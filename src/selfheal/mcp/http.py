"""Token-protected streamable-HTTP transport for the MCP server."""
from __future__ import annotations

import hmac
import os

from .server import create_mcp_server


class BearerAuthMiddleware:
    """ASGI middleware: requires 'Authorization: Bearer <token>'."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            supplied = headers.get(b"authorization", b"").decode()
            expected = f"Bearer {self.token}"
            if not hmac.compare_digest(supplied, expected):
                body = b'{"error":"unauthorized"}'
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def create_secured_http_app(token: str | None = None):
    token = token or os.getenv("SELFHEAL_MCP_TOKEN")
    if not token:
        raise RuntimeError(
            "SELFHEAL_MCP_TOKEN must be set to serve MCP over HTTP"
        )
    return BearerAuthMiddleware(
        create_mcp_server().streamable_http_app(), token
    )
