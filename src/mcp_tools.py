"""
VyaparSathi — MCP Tool Definitions
Registers three agentic capabilities with the MCP server.
Each tool is a thin adapter: validate input → call business logic → return result.
"""

from __future__ import annotations

import logging
from datetime import datetime

from mcp.server.mcpserver import MCPServer

from src.reconciliation import (
    audit_pending_invoices as _audit_pending,
    generate_gst_summary as _generate_gst,
    reconcile_upi_statements as _reconcile_upi,
)
from src.schemas import AuditPendingInput, GSTSummaryInput, ReconcileInput

logger = logging.getLogger("vyaparsathi.mcp_tools")

# ─────────────────────────────────────────────────────────
# MCP Server Instance
# ─────────────────────────────────────────────────────────

mcp = MCPServer(
    name="VyaparSathi",
    instructions=(
        "VyaparSathi is an AI back-office financial agent for small Indian retailers. "
        "It can reconcile UPI payment messages against sales invoices, audit pending "
        "receivables, and generate monthly GST tax summaries. All monetary values are "
        "in Indian Rupees (INR). GST rates are CGST 9% + SGST 9% = 18% total."
    ),
)


# ─────────────────────────────────────────────────────────
# Tool 1: Reconcile UPI Statements
# ─────────────────────────────────────────────────────────

@mcp.tool()
async def reconcile_upi_statements(upi_messages: list[str]) -> dict:
    """
    Reconcile raw UPI payment messages against the sales ledger.

    Accepts an array of unstructured UPI transaction SMS/notification strings,
    parses each to extract amount, transaction ID, and sender, then matches
    them against existing invoices in the database.

    Returns a JSON object with:
    - matched: transactions successfully linked to an invoice
    - orphaned: messages that could not be matched (with reason)
    - match_rate: percentage of messages successfully reconciled

    Example input:
        ["Rs.450 received from Rajesh Kumar via UPI. Ref: UPI20260901000001. 01-09-2026"]
    """
    logger.info("Tool invoked: reconcile_upi_statements (%d messages)", len(upi_messages))

    # Validate through Pydantic schema
    validated = ReconcileInput(upi_messages=upi_messages)
    result = await _reconcile_upi(validated.upi_messages)

    return result.model_dump()


# ─────────────────────────────────────────────────────────
# Tool 2: Audit Pending Invoices
# ─────────────────────────────────────────────────────────

@mcp.tool()
async def audit_pending_invoices(start_date: str, end_date: str) -> dict:
    """
    Audit all unpaid and partially paid invoices within a date range.

    Queries the sales ledger for outstanding receivables and returns
    the aggregated balance grouped by customer, sorted by highest
    outstanding amount first.

    Args:
        start_date: Start of date range in ISO 8601 format (e.g. "2026-09-01")
        end_date: End of date range in ISO 8601 format (e.g. "2026-09-30")

    Returns a JSON object with:
    - customers: per-customer breakdown with invoice details
    - total_outstanding: grand total unpaid in INR
    - invoice_count: number of unpaid invoices found
    """
    logger.info("Tool invoked: audit_pending_invoices (%s to %s)", start_date, end_date)

    # Validate through Pydantic schema
    validated = AuditPendingInput(start_date=start_date, end_date=end_date)

    # Parse ISO date strings into datetime objects
    start_dt = datetime.fromisoformat(validated.start_date)
    end_dt = datetime.fromisoformat(validated.end_date).replace(
        hour=23, minute=59, second=59
    )

    result = await _audit_pending(start_dt, end_dt)

    return result.model_dump()


# ─────────────────────────────────────────────────────────
# Tool 3: Generate GST Summary
# ─────────────────────────────────────────────────────────

@mcp.tool()
async def generate_gst_summary(month: int, year: int) -> dict:
    """
    Generate a monthly GST (Goods & Services Tax) summary for the retailer.

    Aggregates all completed (paid) sales for the specified month and year,
    then computes the tax liabilities:
    - CGST (Central GST) at 9%
    - SGST (State GST) at 9%
    - Total GST = CGST + SGST (18%)

    Args:
        month: Month number (1-12)
        year: Calendar year (e.g. 2026)

    Returns a JSON object with:
    - total_taxable_sales: sum of pre-tax subtotals
    - cgst_liability: Central GST amount owed
    - sgst_liability: State GST amount owed
    - total_gst: combined tax liability
    - invoice_count: number of paid invoices in the period
    """
    logger.info("Tool invoked: generate_gst_summary (%02d/%d)", month, year)

    # Validate through Pydantic schema
    validated = GSTSummaryInput(month=month, year=year)
    result = await _generate_gst(validated.month, validated.year)

    return result.model_dump()
