"""
VyaparSathi — Pydantic Schemas
Strict-typed models for MongoDB documents and MCP tool inputs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────

class InvoiceStatus(str, Enum):
    """Lifecycle states of a sales invoice."""
    PAID = "paid"
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"


class PaymentMode(str, Enum):
    """Supported payment methods for Indian retail."""
    UPI = "upi"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CREDIT = "credit"


# ─────────────────────────────────────────────────────────
# MongoDB Document Models
# ─────────────────────────────────────────────────────────

class Invoice(BaseModel):
    """
    Represents a sales invoice issued by the retailer.
    Maps to the `invoices` collection in MongoDB.
    """
    invoice_id: str = Field(..., description="Unique invoice identifier (e.g. INV-2026-0001)")
    customer_name: str = Field(..., description="Name of the buyer / customer")
    customer_phone: Optional[str] = Field(None, description="Customer mobile number")
    items: list[InvoiceItem] = Field(default_factory=list, description="Line items on the invoice")
    subtotal: float = Field(..., ge=0, description="Pre-tax total in INR")
    cgst: float = Field(0.0, ge=0, description="Central GST amount (9%)")
    sgst: float = Field(0.0, ge=0, description="State GST amount (9%)")
    total: float = Field(..., ge=0, description="Grand total including GST in INR")
    status: InvoiceStatus = Field(InvoiceStatus.UNPAID, description="Payment status")
    payment_mode: Optional[PaymentMode] = Field(None, description="How the customer paid")
    upi_transaction_id: Optional[str] = Field(None, description="UPI ref ID if paid via UPI")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = Field(None, description="Timestamp when payment was received")

    model_config = {"populate_by_name": True}


class InvoiceItem(BaseModel):
    """A single line item within an invoice."""
    name: str = Field(..., description="Product / service name")
    quantity: int = Field(..., ge=1, description="Units sold")
    unit_price: float = Field(..., ge=0, description="Price per unit in INR")
    amount: float = Field(..., ge=0, description="Line total (quantity × unit_price)")


# Rebuild Invoice to resolve the forward reference to InvoiceItem
Invoice.model_rebuild()


class UPITransaction(BaseModel):
    """
    Represents a parsed UPI transaction message.
    Maps to the `upi_transactions` collection in MongoDB.
    """
    transaction_id: str = Field(..., description="UPI reference / UTR number")
    amount: float = Field(..., ge=0, description="Transaction amount in INR")
    sender: str = Field(..., description="Sender name or UPI ID")
    receiver: str = Field(..., description="Receiver name or UPI ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_message: str = Field(..., description="Original unstructured SMS / notification text")
    matched_invoice_id: Optional[str] = Field(
        None, description="Invoice ID this transaction was reconciled to"
    )

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────
# MCP Tool Input Schemas
# ─────────────────────────────────────────────────────────

class ReconcileInput(BaseModel):
    """Input schema for the `reconcile_upi_statements` tool."""
    upi_messages: list[str] = Field(
        ...,
        min_length=1,
        description="Array of raw UPI transaction message strings to reconcile"
    )


class AuditPendingInput(BaseModel):
    """Input schema for the `audit_pending_invoices` tool."""
    start_date: str = Field(
        ...,
        description="Start of date range (ISO 8601, e.g. '2026-09-01')"
    )
    end_date: str = Field(
        ...,
        description="End of date range (ISO 8601, e.g. '2026-09-30')"
    )


class GSTSummaryInput(BaseModel):
    """Input schema for the `generate_gst_summary` tool."""
    month: int = Field(..., ge=1, le=12, description="Month number (1–12)")
    year: int = Field(..., ge=2020, le=2100, description="Calendar year")


# ─────────────────────────────────────────────────────────
# MCP Tool Response Envelopes
# ─────────────────────────────────────────────────────────

class ReconcileResult(BaseModel):
    """Output envelope for UPI reconciliation."""
    matched: list[dict] = Field(default_factory=list, description="Successfully matched transactions")
    orphaned: list[dict] = Field(default_factory=list, description="Unmatched UPI messages")
    match_rate: float = Field(0.0, description="Percentage of messages matched")


class AuditResult(BaseModel):
    """Output envelope for pending invoice audit."""
    customers: list[dict] = Field(default_factory=list, description="Per-customer outstanding breakdown")
    total_outstanding: float = Field(0.0, description="Grand total unpaid in INR")
    invoice_count: int = Field(0, description="Number of unpaid invoices found")


class GSTSummaryResult(BaseModel):
    """Output envelope for GST computation."""
    month: int
    year: int
    total_taxable_sales: float = Field(0.0, description="Sum of subtotals for paid invoices")
    cgst_liability: float = Field(0.0, description="CGST at 9%")
    sgst_liability: float = Field(0.0, description="SGST at 9%")
    total_gst: float = Field(0.0, description="CGST + SGST combined")
    invoice_count: int = Field(0, description="Number of completed invoices in period")
