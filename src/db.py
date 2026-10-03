"""
VyaparSathi — Async MongoDB Client & Seed Data
Handles Motor client lifecycle and populates mock retail data for demo/testing.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger("vyaparsathi.db")

# ─────────────────────────────────────────────────────────
# Singleton Client
# ─────────────────────────────────────────────────────────

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect_db() -> AsyncIOMotorDatabase:
    """
    Initialize the Motor async client and return the database handle.
    Reads connection params from environment variables.
    """
    global _client, _db

    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "vyaparsathi")

    logger.info("Connecting to MongoDB at %s (db=%s)", mongo_uri, db_name)

    _client = AsyncIOMotorClient(mongo_uri)
    _db = _client[db_name]

    # Verify connectivity
    await _client.admin.command("ping")
    logger.info("MongoDB connection established successfully.")

    return _db


async def close_db() -> None:
    """Gracefully close the Motor client."""
    global _client, _db
    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed.")
        _client = None
        _db = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the active database handle. Raises if not connected."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _db


# ─────────────────────────────────────────────────────────
# Collection Accessors
# ─────────────────────────────────────────────────────────

def invoices_collection():
    """Return the `invoices` collection handle."""
    return get_db()["invoices"]


def upi_transactions_collection():
    """Return the `upi_transactions` collection handle."""
    return get_db()["upi_transactions"]


# ─────────────────────────────────────────────────────────
# Index Creation
# ─────────────────────────────────────────────────────────

async def ensure_indexes() -> None:
    """Create indexes for query-heavy fields."""
    inv = invoices_collection()
    await inv.create_index("invoice_id", unique=True)
    await inv.create_index("status")
    await inv.create_index("created_at")
    await inv.create_index("customer_name")

    upi = upi_transactions_collection()
    await upi.create_index("transaction_id", unique=True)
    await upi.create_index("amount")
    await upi.create_index("matched_invoice_id")

    logger.info("Database indexes ensured.")


# ─────────────────────────────────────────────────────────
# Mock Data Seeder
# ─────────────────────────────────────────────────────────

# Realistic Indian retail mock data
_MOCK_CUSTOMERS = [
    {"name": "Rajesh Kumar", "phone": "9876543210"},
    {"name": "Priya Sharma", "phone": "9123456789"},
    {"name": "Amit Patel", "phone": "9988776655"},
    {"name": "Sunita Devi", "phone": "9871234560"},
    {"name": "Vikram Singh", "phone": "9009876543"},
]

_MOCK_PRODUCTS = [
    {"name": "Tata Salt (1kg)", "price": 28.0},
    {"name": "Aashirvaad Atta (5kg)", "price": 275.0},
    {"name": "Fortune Sunflower Oil (1L)", "price": 155.0},
    {"name": "Parle-G Biscuits (800g)", "price": 80.0},
    {"name": "Amul Butter (500g)", "price": 270.0},
    {"name": "Surf Excel (1kg)", "price": 195.0},
    {"name": "Maggi Noodles (12 pack)", "price": 168.0},
    {"name": "Dabur Honey (500g)", "price": 225.0},
    {"name": "Colgate MaxFresh (150g)", "price": 95.0},
    {"name": "Lifebuoy Soap (4 pack)", "price": 132.0},
]

_MOCK_UPI_MESSAGES = [
    "Rs.{amount} received from {sender} via UPI. Ref: {txn_id}. {date}",
    "UPI payment of INR {amount} credited. Txn ID: {txn_id}. From: {sender}. {date}",
    "You have received Rs {amount} from {sender}. UPI Ref No: {txn_id}. Date: {date}",
    "Payment received! Amount: Rs.{amount}, Sender: {sender}, UPI Ref: {txn_id}, Date: {date}",
]


async def seed_mock_data() -> None:
    """
    Populate the database with realistic Indian retail invoices and
    corresponding UPI transaction messages for demo purposes.
    Skips seeding if data already exists.
    """
    inv_col = invoices_collection()
    upi_col = upi_transactions_collection()

    # Guard: skip if already seeded
    existing = await inv_col.count_documents({})
    if existing > 0:
        logger.info("Database already seeded (%d invoices). Skipping.", existing)
        return

    logger.info("Seeding mock retail data...")

    base_date = datetime(2026, 9, 1)
    invoices = []
    upi_transactions = []
    invoice_counter = 0

    for day_offset in range(28):  # 4 weeks of September 2026
        invoice_date = base_date + timedelta(days=day_offset)

        # 2-3 invoices per day
        num_invoices = 2 + (day_offset % 2)

        for i in range(num_invoices):
            invoice_counter += 1
            customer = _MOCK_CUSTOMERS[invoice_counter % len(_MOCK_CUSTOMERS)]

            # Build 1-4 line items
            items = []
            num_items = 1 + (invoice_counter % 4)
            subtotal = 0.0

            for j in range(num_items):
                product = _MOCK_PRODUCTS[(invoice_counter + j) % len(_MOCK_PRODUCTS)]
                qty = 1 + (j % 3)
                line_amount = product["price"] * qty
                subtotal += line_amount
                items.append({
                    "name": product["name"],
                    "quantity": qty,
                    "unit_price": product["price"],
                    "amount": round(line_amount, 2),
                })

            subtotal = round(subtotal, 2)
            cgst = round(subtotal * 0.09, 2)
            sgst = round(subtotal * 0.09, 2)
            total = round(subtotal + cgst + sgst, 2)

            invoice_id = f"INV-2026-{invoice_counter:04d}"

            # ~60% paid, ~30% unpaid, ~10% partially paid
            if invoice_counter % 10 < 6:
                status = "paid"
                payment_mode = "upi" if invoice_counter % 3 != 0 else "cash"
            elif invoice_counter % 10 < 9:
                status = "unpaid"
                payment_mode = None
            else:
                status = "partially_paid"
                payment_mode = "upi"

            txn_id = f"UPI{invoice_date.strftime('%Y%m%d')}{invoice_counter:06d}"

            invoice = {
                "invoice_id": invoice_id,
                "customer_name": customer["name"],
                "customer_phone": customer["phone"],
                "items": items,
                "subtotal": subtotal,
                "cgst": cgst,
                "sgst": sgst,
                "total": total,
                "status": status,
                "payment_mode": payment_mode,
                "upi_transaction_id": txn_id if payment_mode == "upi" else None,
                "created_at": invoice_date,
                "paid_at": invoice_date if status == "paid" else None,
            }
            invoices.append(invoice)

            # Generate matching UPI message for UPI-paid invoices
            if payment_mode == "upi":
                template = _MOCK_UPI_MESSAGES[invoice_counter % len(_MOCK_UPI_MESSAGES)]
                raw_msg = template.format(
                    amount=total,
                    sender=customer["name"],
                    txn_id=txn_id,
                    date=invoice_date.strftime("%d-%m-%Y"),
                )
                upi_txn = {
                    "transaction_id": txn_id,
                    "amount": total,
                    "sender": customer["name"],
                    "receiver": "MyKiranaStore@upi",
                    "timestamp": invoice_date,
                    "raw_message": raw_msg,
                    "matched_invoice_id": invoice_id if status == "paid" else None,
                }
                upi_transactions.append(upi_txn)

    # Also add some "orphaned" UPI messages (no matching invoice)
    orphan_messages = [
        {
            "transaction_id": "UPI20260915999001",
            "amount": 450.0,
            "sender": "Unknown Sender",
            "receiver": "MyKiranaStore@upi",
            "timestamp": datetime(2026, 9, 15),
            "raw_message": "Rs.450 received from Unknown Sender via UPI. Ref: UPI20260915999001. 15-09-2026",
            "matched_invoice_id": None,
        },
        {
            "transaction_id": "UPI20260920999002",
            "amount": 1200.0,
            "sender": "Ramesh Gupta",
            "receiver": "MyKiranaStore@upi",
            "timestamp": datetime(2026, 9, 20),
            "raw_message": "UPI payment of INR 1200.0 credited. Txn ID: UPI20260920999002. From: Ramesh Gupta. 20-09-2026",
            "matched_invoice_id": None,
        },
        {
            "transaction_id": "UPI20260925999003",
            "amount": 89.0,
            "sender": "Meena Kumari",
            "receiver": "MyKiranaStore@upi",
            "timestamp": datetime(2026, 9, 25),
            "raw_message": "You have received Rs 89.0 from Meena Kumari. UPI Ref No: UPI20260925999003. Date: 25-09-2026",
            "matched_invoice_id": None,
        },
    ]
    upi_transactions.extend(orphan_messages)

    # Bulk insert
    if invoices:
        await inv_col.insert_many(invoices)
        logger.info("Seeded %d invoices.", len(invoices))

    if upi_transactions:
        await upi_col.insert_many(upi_transactions)
        logger.info("Seeded %d UPI transactions.", len(upi_transactions))

    # Create indexes after seeding
    await ensure_indexes()

    logger.info("Mock data seeding complete.")
