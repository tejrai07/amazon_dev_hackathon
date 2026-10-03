# VyaparSathi — MCP Financial Agent for Indian Retailers

> Self-hosted MCP server that acts as an AI back-office financial agent for small Indian retailers.  
> Built for the **Amazon Developer Hackathon 2026 — Alexa+ Track**.

## Architecture

```
┌──────────────┐      SSE/JSON-RPC       ┌──────────────────┐      Async Motor      ┌──────────┐
│  MCP Client  │  ◄──────────────────►   │  VyaparSathi     │  ◄────────────────►   │ MongoDB  │
│  (Alexa+)    │                          │  FastAPI + MCP   │                        │  7.x     │
└──────────────┘                          └──────────────────┘                        └──────────┘
```

## MCP Tools

| Tool                        | Purpose                                          |
|-----------------------------|--------------------------------------------------|
| `reconcile_upi_statements`  | Match UPI messages against sales invoices         |
| `audit_pending_invoices`    | Aggregate unpaid invoices by customer              |
| `generate_gst_summary`     | Compute monthly CGST/SGST liabilities              |

## Quick Start

```bash
docker compose up --build
```

The MCP SSE endpoint will be available at `http://localhost:8000/mcp`.

## Tech Stack

- **Python 3.11+** / FastAPI / Uvicorn
- **MCP SDK** (SSE transport)
- **MongoDB 7** (async via Motor)
- **Docker / Docker Compose** (EC2-optimized)
