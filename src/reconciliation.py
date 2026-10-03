"""
VyaparSathi — Core Business Logic
Pure async functions for reconciliation, audit, and GST computation.
No transport or MCP concerns — called by the tool layer.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from src.db import invoices_collection, upi_transactions_collection
from src.schemas import (
    AuditResult,
    GSTSummaryResult,
    ReconcileResult,
)

logger = logging.getLogger("vyaparsathi.reconciliation")


# ─────────────────────────────────────────────────────────
# 1. UPI Statement Reconciliation
# ─────────────────────────────────────────────────────────

# Regex patterns to extract structured data from raw UPI SMS messages
_AMOUNT_PATTERNS = [
    re.compile(r"Rs\.?\s*([\d,]+(?:\.\d{1,2})?)"),            # Rs.450 / Rs 1,200.50
    re.compile(r"INR\s*([\d,]+(?:\.\d{1,2})?)"),               # INR 450
    re.compile(r"Amount:\s*Rs\.?\s*([\d,]+(?:\.\d{1,2})?)"),   # Amount: Rs.450
]

_TXN_ID_PATTERNS = [
    re.compile(r"Ref(?:\s*No)?[:\s]+(\S+)", re.IGNORECASE),    # Ref: UPI123 / Ref No: UPI123
    re.compile(r"Txn\s*ID[:\s]+(\S+)", re.IGNORECASE),         # Txn ID: UPI123
    re.compile(r"UPI\s*Ref[:\s]+(\S+)", re.IGNORECASE),        # UPI Ref: UPI123
]

_SENDER_PATTERNS = [
    re.compile(r"(?:from|From|FROM)\s+(.+?)(?:\s+via|\s*\.\s|\s*,)", re.IGNORECASE),
    re.compile(r"Sender:\s*(.+?)(?:\s*,|\s*\.|\s*$)", re.IGNORECASE),
]


def _parse_upi_message(raw_message: str) -> dict[str, Any]:
    """
    Extract amount, transaction ID, and sender from an unstructured
    UPI payment notification string.
    """
    parsed: dict[str, Any] = {
        "raw_message": raw_message,
        "amount": None,
        "transaction_id": None,
        "sender": None,
    }

    # Extract amount
    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(raw_message)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                parsed["amount"] = float(amount_str)
            except ValueError:
                continue
            break

    # Extract transaction ID
    for pattern in _TXN_ID_PATTERNS:
        match = pattern.search(raw_message)
        if match:
            # Strip trailing punctuation from captured ID
            txn_id = match.group(1).rstrip(".,;:")
            parsed["transaction_id"] = txn_id
            break

    # Extract sender
    for pattern in _SENDER_PATTERNS:
        match = pattern.search(raw_message)
        if match:
            parsed["sender"] = match.group(1).strip()
            break

    return parsed


async def reconcile_upi_statements(upi_messages: list[str]) -> ReconcileResult:
    """
    Reconcile raw UPI SMS/notification strings against the sales ledger.

    Strategy (in priority order):
      1. Exact match on transaction_id against invoice.upi_transaction_id
      2. Fuzzy match on amount against unpaid/partially_paid invoices

    Returns a ReconcileResult with matched, orphaned, and match rate.
    """
    inv_col = invoices_collection()
    upi_col = upi_transactions_collection()

    matched: list[dict] = []
    orphaned: list[dict] = []

    for raw_msg in upi_messages:
        parsed = _parse_upi_message(raw_msg)
        txn_id = parsed.get("transaction_id")
        amount = parsed.get("amount")

        match_result: dict[str, Any] | None = None

        # ── Strategy 1: Exact match on transaction ID ────────
        if txn_id:
            invoice = await inv_col.find_one({"upi_transaction_id": txn_id})
            if invoice:
                match_result = {
                    "upi_transaction_id": txn_id,
                    "invoice_id": invoice["invoice_id"],
                    "invoice_total": invoice["total"],
                    "upi_amount": amount,
                    "customer_name": invoice["customer_name"],
                    "match_type": "exact_txn_id",
                    "status": "confirmed",
                }

        # ── Strategy 2: Amount-based match on unpaid invoices ─
        if match_result is None and amount is not None:
            # Find unpaid invoices with a matching total (tolerance ±0.50 INR)
            candidate = await inv_col.find_one({
                "status": {"$in": ["unpaid", "partially_paid"]},
                "total": {"$gte": amount - 0.50, "$lte": amount + 0.50},
            })
            if candidate:
                match_result = {
                    "upi_transaction_id": txn_id,
                    "invoice_id": candidate["invoice_id"],
                    "invoice_total": candidate["total"],
                    "upi_amount": amount,
                    "customer_name": candidate["customer_name"],
                    "match_type": "amount_fuzzy",
                    "status": "needs_review",
                }
                # Mark invoice as paid
                await inv_col.update_one(
                    {"_id": candidate["_id"]},
                    {"$set": {
                        "status": "paid",
                        "payment_mode": "upi",
                        "upi_transaction_id": txn_id,
                        "paid_at": datetime.utcnow(),
                    }},
                )

        if match_result:
            matched.append(match_result)

            # Persist the parsed UPI transaction if it doesn't already exist
            if txn_id:
                existing = await upi_col.find_one({"transaction_id": txn_id})
                if not existing:
                    await upi_col.insert_one({
                        "transaction_id": txn_id,
                        "amount": amount,
                        "sender": parsed.get("sender", "Unknown"),
                        "receiver": "MyKiranaStore@upi",
                        "timestamp": datetime.utcnow(),
                        "raw_message": raw_msg,
                        "matched_invoice_id": match_result["invoice_id"],
                    })
        else:
            orphaned.append({
                "raw_message": raw_msg,
                "parsed_amount": amount,
                "parsed_txn_id": txn_id,
                "parsed_sender": parsed.get("sender"),
                "reason": _classify_orphan_reason(txn_id, amount),
            })

    total = len(upi_messages)
    match_rate = round((len(matched) / total) * 100, 2) if total > 0 else 0.0

    logger.info(
        "Reconciliation complete: %d matched, %d orphaned (%.1f%% rate)",
        len(matched), len(orphaned), match_rate,
    )

    return ReconcileResult(
        matched=matched,
        orphaned=orphaned,
        match_rate=match_rate,
    )


def _classify_orphan_reason(txn_id: str | None, amount: float | None) -> str:
    """Provide a human-readable reason why a UPI message couldn't be matched."""
    if txn_id is None and amount is None:
        return "Could not parse transaction ID or amount from message"
    if txn_id is None:
        return "Transaction ID could not be extracted; amount-based match found no candidates"
    if amount is None:
        return "Amount could not be extracted; transaction ID not found in invoices"
    return "No matching invoice found for this transaction ID or amount"


# ─────────────────────────────────────────────────────────
# 2. Pending Invoice Audit
# ─────────────────────────────────────────────────────────

async def audit_pending_invoices(
    start_date: datetime,
    end_date: datetime,
) -> AuditResult:
    """
    Query all unpaid / partially_paid invoices within a date range
    and aggregate outstanding balances grouped by customer.
    """
    inv_col = invoices_collection()

    pipeline = [
        # Stage 1: Filter by status and date range
        {
            "$match": {
                "status": {"$in": ["unpaid", "partially_paid"]},
                "created_at": {"$gte": start_date, "$lte": end_date},
            }
        },
        # Stage 2: Group by customer
        {
            "$group": {
                "_id": "$customer_name",
                "total_outstanding": {"$sum": "$total"},
                "invoice_count": {"$sum": 1},
                "invoices": {
                    "$push": {
                        "invoice_id": "$invoice_id",
                        "total": "$total",
                        "created_at": {"$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at",
                        }},
                        "status": "$status",
                    }
                },
            }
        },
        # Stage 3: Sort by outstanding amount descending
        {"$sort": {"total_outstanding": -1}},
    ]

    cursor = inv_col.aggregate(pipeline)
    results = await cursor.to_list(length=None)

    customers = []
    grand_total = 0.0
    total_invoices = 0

    for doc in results:
        customer_entry = {
            "customer_name": doc["_id"],
            "total_outstanding": round(doc["total_outstanding"], 2),
            "invoice_count": doc["invoice_count"],
            "invoices": doc["invoices"],
        }
        customers.append(customer_entry)
        grand_total += doc["total_outstanding"]
        total_invoices += doc["invoice_count"]

    logger.info(
        "Audit complete: %d customers, %d invoices, ₹%.2f outstanding",
        len(customers), total_invoices, grand_total,
    )

    return AuditResult(
        customers=customers,
        total_outstanding=round(grand_total, 2),
        invoice_count=total_invoices,
    )


# ─────────────────────────────────────────────────────────
# 3. GST Summary Generation
# ─────────────────────────────────────────────────────────

async def generate_gst_summary(month: int, year: int) -> GSTSummaryResult:
    """
    Aggregate all completed (paid) sales for a given month/year
    and compute CGST (9%) + SGST (9%) liabilities.

    Uses pre-computed cgst/sgst fields on invoices when available,
    falls back to calculating from subtotals.
    """
    inv_col = invoices_collection()

    # Build date boundaries for the target month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    pipeline = [
        # Only completed sales
        {
            "$match": {
                "status": "paid",
                "paid_at": {"$gte": start_date, "$lt": end_date},
            }
        },
        # Aggregate totals
        {
            "$group": {
                "_id": None,
                "total_taxable_sales": {"$sum": "$subtotal"},
                "total_cgst": {"$sum": "$cgst"},
                "total_sgst": {"$sum": "$sgst"},
                "invoice_count": {"$sum": 1},
            }
        },
    ]

    cursor = inv_col.aggregate(pipeline)
    results = await cursor.to_list(length=1)

    if not results:
        logger.info("No paid invoices found for %02d/%d.", month, year)
        return GSTSummaryResult(
            month=month,
            year=year,
            total_taxable_sales=0.0,
            cgst_liability=0.0,
            sgst_liability=0.0,
            total_gst=0.0,
            invoice_count=0,
        )

    agg = results[0]
    taxable = round(agg["total_taxable_sales"], 2)
    cgst = round(agg["total_cgst"], 2)
    sgst = round(agg["total_sgst"], 2)

    # Fallback: if stored GST fields are zero, recompute from subtotals
    if cgst == 0.0 and sgst == 0.0 and taxable > 0:
        cgst = round(taxable * 0.09, 2)
        sgst = round(taxable * 0.09, 2)

    total_gst = round(cgst + sgst, 2)

    logger.info(
        "GST summary for %02d/%d: ₹%.2f taxable, ₹%.2f CGST, ₹%.2f SGST (%d invoices)",
        month, year, taxable, cgst, sgst, agg["invoice_count"],
    )

    return GSTSummaryResult(
        month=month,
        year=year,
        total_taxable_sales=taxable,
        cgst_liability=cgst,
        sgst_liability=sgst,
        total_gst=total_gst,
        invoice_count=agg["invoice_count"],
    )
