"""Opt-in bearer-authenticated Streamable HTTP. Deploy behind HTTPS remotely."""
import hmac
import os


class BearerAuth:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            expected = ("Bearer " + self.token).encode()
            if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"www-authenticate", b"Bearer"), (b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await self.app(scope, receive, send)


def serve(mcp, host, port):
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings
    token = os.environ.get("ZEROINFER_MCP_TOKEN", "")
    if len(token) < 32:
        raise ValueError("Set ZEROINFER_MCP_TOKEN to a random token of at least 32 characters for HTTP transport")
    # HTTP clients must upload their inputs; they cannot select server filesystem paths.
    os.environ["ZEROINFER_MCP_REMOTE"] = "1"
    mcp.settings.host, mcp.settings.port = host, port
    mcp.settings.stateless_http = True
    allowed = [h.strip() for h in os.environ.get("ZEROINFER_MCP_ALLOWED_HOSTS", "127.0.0.1:*,localhost:*").split(",") if h.strip()]
    origins = [o.strip() for o in os.environ.get("ZEROINFER_MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                                               allowed_hosts=allowed, allowed_origins=origins)
    uvicorn.run(BearerAuth(mcp.streamable_http_app(), token), host=host, port=port)
