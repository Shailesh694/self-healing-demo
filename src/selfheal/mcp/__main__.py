"""
Launch the Self-Healing MCP server.

  python -m selfheal.mcp                 # stdio (local, process-trusted)
  python -m selfheal.mcp streamable-http # HTTP, requires SELFHEAL_MCP_TOKEN
"""
from __future__ import annotations

import os
import sys

from .server import mcp_server


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "streamable-http":
        import uvicorn

        from .http import create_secured_http_app

        uvicorn.run(
            create_secured_http_app(),
            host=os.getenv("SELFHEAL_MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("SELFHEAL_MCP_PORT", "8765")),
        )
        return
    try:
        mcp_server.run(transport=transport)
    except KeyboardInterrupt:
        pass  # clean Ctrl+C exit


if __name__ == "__main__":
    main()
