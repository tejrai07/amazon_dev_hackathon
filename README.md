# 🛒 VyaparSathi — MCP Financial Agent for Indian Retailers

> Self-hosted MCP server that acts as an **AI back-office financial agent** for small Indian retailers.  
> Built for the **Amazon Developer Hackathon 2026 — Alexa+ Track**.

VyaparSathi gives retailers a voice-first financial assistant through Alexa+. Speak naturally — *"Alexa, reconcile today's UPI payments"* — and the agent reconciles transactions, audits outstanding invoices, and computes GST liabilities in real time.

---

## 🏗️ Architecture Overview

```
                         Internet
                            │
                   ┌────────▼────────┐
                   │   DuckDNS       │
                   │ vyaparsathi.    │
                   │ duckdns.org     │
                   └────────┬────────┘
                            │ DNS → EC2 Public IP
                   ┌────────▼────────┐
                   │  AWS EC2        │
                   │  (Ubuntu 24.04) │
                   │  t2.micro       │
                   └────────┬────────┘
                            │
              ┌─────────────┼──────────────┐
              │     Docker Compose Stack   │
              │                            │
              │  ┌───────────────────────┐  │
     :80/:443 │  │   Nginx (Alpine)     │  │  TLS Termination
    ─────────►│  │   Reverse Proxy      │  │  HTTP → HTTPS redirect
              │  │   + Let's Encrypt    │  │  SSE stream passthrough
              │  └──────────┬───────────┘  │
              │             │ :8000        │
              │  ┌──────────▼───────────┐  │
              │  │   VyaparSathi        │  │  MCP Streamable HTTP
              │  │   FastAPI + Uvicorn  │  │  JSON-RPC 2.0 over HTTPS
              │  └──────────┬───────────┘  │
              │             │ :27017       │
              │  ┌──────────▼───────────┐  │
              │  │   MongoDB 7          │  │  Async via Motor
              │  │   (Persistent Vol)   │  │  Sales ledger + invoices
              │  └───────────────────────┘  │
              │                            │
              └────────────────────────────┘
```

---

## 🔧 MCP Tools

| Tool | Purpose | Example Prompt |
|------|---------|----------------|
| `reconcile_upi_statements` | Match UPI payment SMS/notifications against sales invoices | *"Reconcile these 5 UPI messages"* |
| `audit_pending_invoices` | Aggregate unpaid invoices by customer in a date range | *"Show outstanding receivables for September"* |
| `generate_gst_summary` | Compute monthly CGST (9%) + SGST (9%) liabilities | *"Generate GST summary for Sep 2026"* |

All tools accept structured JSON-RPC calls via MCP's Streamable HTTP transport and return detailed JSON responses.

---

## ☁️ AWS Cloud Deployment

### Infrastructure Setup

| Component | Configuration |
|-----------|--------------|
| **EC2 Instance** | Ubuntu 24.04 LTS, t2.micro (Free Tier eligible) |
| **Region** | AWS default VPC |
| **Public IP** | Elastic/dynamic IP assigned to the instance |
| **Domain** | `vyaparsathi.duckdns.org` (free DDNS via DuckDNS) |
| **SSL/TLS** | Let's Encrypt (Certbot, auto-renewing) |
| **Containers** | Docker Compose (3-service stack) |

### Networking & Security

#### Security Group — Inbound Rules

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | My IP | SSH access for deployment |
| 80 | TCP | 0.0.0.0/0 | HTTP → HTTPS redirect + ACME challenges |
| 443 | TCP | 0.0.0.0/0 | HTTPS (MCP Streamable HTTP endpoint) |

> **Note:** MongoDB (27017) and the FastAPI app (8000) are **not exposed** to the internet. They communicate only within the Docker bridge network (`vyapar-net`).

#### DNS Configuration

```
vyaparsathi.duckdns.org  →  A record  →  EC2 Public IP
```

DuckDNS provides a free dynamic DNS subdomain. Updated via:
```bash
curl "https://www.duckdns.org/update?domains=vyaparsathi&token=<TOKEN>&ip=<EC2_PUBLIC_IP>"
```

#### TLS Certificate (Let's Encrypt)

```bash
# Issue certificate using standalone mode
sudo certbot certonly --standalone -d vyaparsathi.duckdns.org

# Certificates stored at:
# /etc/letsencrypt/live/vyaparsathi.duckdns.org/fullchain.pem
# /etc/letsencrypt/live/vyaparsathi.duckdns.org/privkey.pem

# Copy to project for Nginx volume mount
mkdir -p ssl/
sudo cp /etc/letsencrypt/live/vyaparsathi.duckdns.org/fullchain.pem ssl/
sudo cp /etc/letsencrypt/live/vyaparsathi.duckdns.org/privkey.pem ssl/
```

Certbot automatically schedules renewal — certificates are valid for 90 days.

### Nginx Reverse Proxy

The Nginx container handles:

- **TLS termination** — decrypts HTTPS, forwards plain HTTP to the FastAPI container
- **HTTP → HTTPS redirect** — all port 80 traffic is 301-redirected to HTTPS
- **SSE stream passthrough** — `proxy_buffering off` ensures Server-Sent Events for MCP Streamable HTTP arrive immediately without Nginx holding them
- **ACME challenge support** — `/well-known/acme-challenge/` is routed to the certbot webroot for automated renewal
- **Host header rewriting** — sends `Host: localhost` to upstream to satisfy the MCP SDK's DNS rebinding protection

Key Nginx directives for MCP/SSE:
```nginx
proxy_buffering    off;
proxy_cache        off;
proxy_read_timeout 3600s;   # 1-hour timeout for long SSE streams
proxy_set_header   Host localhost;  # MCP SDK host validation
```

---

## 🚀 Deployment Guide

### Prerequisites

- AWS EC2 instance (Ubuntu 22.04+ recommended)
- Docker & Docker Compose installed
- Domain pointing to your EC2 public IP
- SSL certificate (Let's Encrypt)

### Step 1: SSH into EC2

```bash
ssh -i "path/to/your-key.pem" ubuntu@<EC2_PUBLIC_IP>
```

### Step 2: Clone the Repository

```bash
git clone https://github.com/tejrai07/amazon_dev_hackathon.git
cd amazon_dev_hackathon
```

### Step 3: Configure Environment

```bash
cat > .env << 'EOF'
MONGO_PASSWORD=<your_secure_password>
MONGO_USER=vyapar_admin
MONGO_DB_NAME=vyaparsathi
SEED_DATA=true
EOF
```

### Step 4: Set Up SSL Certificates

```bash
# Issue cert (stop any service on port 80 first)
sudo certbot certonly --standalone -d vyaparsathi.duckdns.org

# Copy to project
mkdir -p ssl/
sudo cp /etc/letsencrypt/live/vyaparsathi.duckdns.org/fullchain.pem ssl/
sudo cp /etc/letsencrypt/live/vyaparsathi.duckdns.org/privkey.pem ssl/
sudo chmod 644 ssl/*.pem
```

### Step 5: Deploy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 6: Verify

```bash
# Health check
curl https://vyaparsathi.duckdns.org/nginx-health

# Test MCP endpoint
curl -X POST https://vyaparsathi.duckdns.org/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

---

## 💻 Local Development

```bash
# Start MongoDB + FastAPI (no TLS, no Nginx)
docker compose up --build

# MCP endpoint available at http://localhost:8000/mcp
```

---

## 📁 Project Structure

```
amazon_dev_hackathon/
├── src/
│   ├── main.py              # FastAPI app + MCP Streamable HTTP mount
│   ├── mcp_tools.py         # MCP tool definitions (3 financial tools)
│   ├── reconciliation.py    # Business logic (UPI matching, GST calc)
│   ├── schemas.py           # Pydantic input/output validation
│   ├── db.py                # MongoDB async connection (Motor)
│   └── __init__.py
├── tests/
│   ├── test_mcp_client.py   # MCP client integration tests
│   └── __init__.py
├── Dockerfile               # Python 3.11-slim, non-root user
├── docker-compose.yml       # Dev stack (Mongo + FastAPI)
├── docker-compose.prod.yml  # Prod stack (Mongo + FastAPI + Nginx TLS)
├── nginx.conf               # Reverse proxy with SSE passthrough
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
└── .gitignore
```

---

## 🛡️ Security Considerations

| Measure | Implementation |
|---------|---------------|
| **TLS Encryption** | Let's Encrypt certificate with auto-renewal |
| **Non-root container** | App runs as `vyapar` user (UID 1000) |
| **No exposed DB** | MongoDB accessible only within Docker network |
| **Env-based secrets** | Credentials via `.env` (git-ignored) |
| **Security headers** | HSTS, X-Frame-Options, X-Content-Type-Options |
| **DNS rebinding protection** | MCP SDK host validation + Nginx header rewrite |

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.11 / FastAPI / Uvicorn |
| **Protocol** | MCP Streamable HTTP (JSON-RPC 2.0) |
| **Database** | MongoDB 7 (async via Motor) |
| **Proxy** | Nginx Alpine (TLS + SSE passthrough) |
| **Infra** | AWS EC2 / Docker Compose |
| **DNS** | DuckDNS (free dynamic DNS) |
| **SSL** | Let's Encrypt / Certbot |
| **Validation** | Pydantic v2 |

---

## 📜 License

Built for the **Amazon Developer Hackathon 2026**.

---

*VyaparSathi — व्यापारसाथी — Your business companion* 🇮🇳
