"""
VyaparSathi — FastAPI Application & SSE Transport
Entrypoint: binds the MCP server to a Streamable HTTP endpoint and manages lifecycle.
"""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.db import close_db, connect_db, seed_mock_data
from src.mcp_tools import mcp

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vyaparsathi.main")

# ─────────────────────────────────────────────────────────
# MCP Streamable HTTP App
# ─────────────────────────────────────────────────────────

# Build the ASGI sub-app for MCP's Streamable HTTP transport.
# The `path` argument sets the endpoint *within* the mounted sub-app.
mcp_app = mcp.streamable_http_app()


# ─────────────────────────────────────────────────────────
# Combined Lifespan (FastAPI + MCP session manager)
# ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: connect to MongoDB, optionally seed data, start MCP session manager.
    Shutdown: close the MongoDB connection and MCP sessions.
    """
    logger.info("=" * 60)
    logger.info("VyaparSathi MCP Server — Starting Up")
    logger.info("=" * 60)

    # Connect to MongoDB
    await connect_db()

    # Seed mock data if enabled
    if os.getenv("SEED_DATA", "false").lower() in ("true", "1", "yes"):
        await seed_mock_data()

    logger.info("MCP Streamable HTTP endpoint available at /mcp")
    logger.info("=" * 60)

    # Combine our lifespan with the MCP sub-app's lifespan
    # so the MCP session manager starts/stops correctly.
    async with AsyncExitStack() as stack:
        if mcp_app.router.lifespan_context is not None:
            await stack.enter_async_context(
                mcp_app.router.lifespan_context(mcp_app)
            )
        yield  # ← Application runs here

    logger.info("VyaparSathi MCP Server — Shutting Down")
    await close_db()


# ─────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────

app = FastAPI(
    title="VyaparSathi",
    description=(
        "AI back-office financial agent for small Indian retailers. "
        "Exposes MCP tools for UPI reconciliation, invoice audit, "
        "and GST computation via Streamable HTTP transport."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────
# Allow all origins for hackathon/dev. Tighten for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────
# Health Endpoint (used by Docker HEALTHCHECK)
# ─────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health_check():
    """Liveness probe for Docker / load balancers."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "VyaparSathi",
            "version": "1.0.0",
        },
    )


# ─────────────────────────────────────────────────────────
# Mount MCP Streamable HTTP Transport
# ─────────────────────────────────────────────────────────

app.mount("", mcp_app)

logger.info("MCP tools registered: %s", [
    "reconcile_upi_statements",
    "audit_pending_invoices",
    "generate_gst_summary",
])
