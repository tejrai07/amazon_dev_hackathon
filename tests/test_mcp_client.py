"""
VyaparSathi — MCP Client Smoke Test
Connects to the local Streamable HTTP endpoint, initialises a session,
and verifies that all three tools are registered.

Usage:
    python -m tests.test_mcp_client          # default: http://localhost:8000/mcp
    python -m tests.test_mcp_client http://192.168.1.5:8000/mcp
"""

from __future__ import annotations

import asyncio
import sys

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------

DEFAULT_URL = "http://localhost:8000/mcp"

EXPECTED_TOOLS = {
    "reconcile_upi_statements",
    "audit_pending_invoices",
    "generate_gst_summary",
}


# ---------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------

async def run_smoke_test(url: str) -> None:
    """Connect via Streamable HTTP, list tools, and verify registration."""

    print(f"\n{'=' * 60}")
    print(f"  VyaparSathi MCP Client -- Smoke Test")
    print(f"  Endpoint: {url}")
    print(f"{'=' * 60}\n")

    # -- Step 1: Connect via Streamable HTTP --
    print("[1/3] Connecting to MCP Streamable HTTP endpoint ...")
    async with streamable_http_client(url) as (read_stream, write_stream):
        # -- Step 2: Initialise MCP session --
        async with ClientSession(read_stream, write_stream) as session:
            print("[2/3] Initialising MCP session ...")
            await session.initialize()
            print("      [OK] Session initialised successfully\n")

            # -- Step 3: List registered tools --
            print("[3/3] Listing registered tools ...")
            result = await session.list_tools()

            tool_names: set[str] = set()
            print(f"\n      {'Tool Name':<35} {'Description'}")
            print(f"      {'-' * 35} {'-' * 45}")

            for tool in result.tools:
                tool_names.add(tool.name)
                desc = (tool.description or "")[:45]
                print(f"      {tool.name:<35} {desc}")

            # -- Verify expected tools --
            print()
            missing = EXPECTED_TOOLS - tool_names
            extra = tool_names - EXPECTED_TOOLS

            if missing:
                print(f"  [FAIL] MISSING tools: {', '.join(sorted(missing))}")
            if extra:
                print(f"  [INFO] Extra tools found: {', '.join(sorted(extra))}")
            if not missing:
                print("  [OK] All expected tools are registered!")

    # -- Summary --
    print(f"\n{'=' * 60}")
    if missing:
        print("  RESULT: FAIL -- missing tools detected")
        print(f"{'=' * 60}\n")
        sys.exit(1)
    else:
        print("  RESULT: PASS -- MCP server is healthy")
        print(f"{'=' * 60}\n")


# ---------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------

def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    asyncio.run(run_smoke_test(url))


if __name__ == "__main__":
    main()

