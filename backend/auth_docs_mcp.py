"""
One-time authentication script for the Appian Docs MCP server.

Run this once to complete the OAuth browser login flow.
Tokens are saved to .tokens/appian-docs/ and reused by the backend automatically.

Usage:
    py auth_docs_mcp.py
"""

import asyncio
import webbrowser
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import httpx2
from pydantic import AnyUrl

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, AuthorizationCodeResult
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata

from app.oauth_storage import FileTokenStorage
from app.config import get_settings

# Local callback server config
CALLBACK_PORT = 3030
CALLBACK_URL = f"http://localhost:{CALLBACK_PORT}/callback"

# Shared state for the callback
_auth_result: AuthorizationCodeResult | None = None
_auth_event = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth redirect."""

    def do_GET(self):
        global _auth_result
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _auth_result = AuthorizationCodeResult(
                code=params["code"][0],
                state=params["state"][0] if "state" in params else "",
                iss=params["iss"][0] if "iss" in params else None,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;text-align:center;padding:60px;">
                <h1>Authenticated!</h1>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Error: no code received</h1></body></html>")

        _auth_event.set()

    def log_message(self, format, *args):
        pass  # Suppress log noise


async def open_browser(authorization_url: str) -> None:
    """Open the user's browser to the auth URL."""
    print(f"\nOpening browser for authentication...")
    print(f"If it doesn't open automatically, visit:\n  {authorization_url}\n")
    webbrowser.open(authorization_url)


async def wait_for_callback() -> AuthorizationCodeResult:
    """Wait for the OAuth callback to arrive on our local server."""
    print("Waiting for authentication callback...")

    # Wait in a non-blocking way
    while not _auth_event.is_set():
        await asyncio.sleep(0.1)

    if _auth_result is None:
        raise RuntimeError("No auth result received")

    print("Callback received!")
    return _auth_result


async def main():
    settings = get_settings()
    server_url = settings.appian_docs_url
    storage = FileTokenStorage("appian-docs")

    print(f"Authenticating with: {server_url}")
    print(f"Tokens will be saved to: .tokens/appian-docs/\n")

    # Check if we already have valid tokens
    existing_tokens = await storage.get_tokens()
    if existing_tokens:
        print("Found existing tokens. Testing if they're still valid...")
        # Try to use them
        try:
            oauth = OAuthClientProvider(
                server_url=server_url,
                client_metadata=OAuthClientMetadata(
                    client_name="Appian AI Copilot Backend",
                    redirect_uris=[AnyUrl(CALLBACK_URL)],
                ),
                storage=storage,
                redirect_handler=open_browser,
                callback_handler=wait_for_callback,
            )
            async with httpx2.AsyncClient(auth=oauth, follow_redirects=True) as http_client:
                async with streamable_http_client(server_url, http_client=http_client) as (r, w):
                    async with ClientSession(r, w) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        print(f"\nAlready authenticated! {len(tools.tools)} tools available:")
                        for t in tools.tools[:5]:
                            print(f"  - {t.name}")
                        print("\nNo re-authentication needed.")
                        return
        except Exception as e:
            print(f"Existing tokens expired or invalid: {e}")
            print("Starting fresh authentication...\n")

    # Start local callback server in a thread
    callback_server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    server_thread = threading.Thread(target=callback_server.serve_forever, daemon=True)
    server_thread.start()
    print(f"Callback server listening on {CALLBACK_URL}")

    try:
        oauth = OAuthClientProvider(
            server_url=server_url,
            client_metadata=OAuthClientMetadata(
                client_name="Appian AI Copilot Backend",
                redirect_uris=[AnyUrl(CALLBACK_URL)],
            ),
            storage=storage,
            redirect_handler=open_browser,
            callback_handler=wait_for_callback,
        )

        async with httpx2.AsyncClient(auth=oauth, follow_redirects=True) as http_client:
            async with streamable_http_client(server_url, http_client=http_client) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    print(f"\nAuthentication successful! {len(tools.tools)} tools available:")
                    for t in tools.tools:
                        print(f"  - {t.name}: {t.description[:80] if t.description else ''}")
                    print("\nTokens saved. The backend will use them automatically.")

    finally:
        callback_server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
