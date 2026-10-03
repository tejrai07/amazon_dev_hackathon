# ─────────────────────────────────────────────────────────
# VyaparSathi — Lightweight Production Image
# Base: python:3.11-slim (Debian Bookworm, ~150MB)
# ─────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Create non-root user ────────────────────────────────
RUN groupadd --gid 1000 vyapar && \
    useradd  --uid 1000 --gid vyapar --shell /bin/bash --create-home vyapar

WORKDIR /app

# ── Install Python deps (cached layer) ──────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy application source ─────────────────────────────
COPY src/ ./src/

# ── Drop privileges ─────────────────────────────────────
USER vyapar

EXPOSE 8000

# Health-check: hit the FastAPI /health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── Entrypoint ───────────────────────────────────────────
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
