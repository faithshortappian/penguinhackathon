"""Client for the Appian Docs MCP using OAuth authentication.

The docs MCP server requires OAuth (browser-based login via Google/GitHub).
Run `py auth_docs_mcp.py` once to complete the login flow.
Tokens are then persisted and reused automatically.
"""

import logging
import httpx2
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata
from pydantic import AnyUrl
from app.config import get_settings
from app.oauth_storage import FileTokenStorage

logger = logging.getLogger("app.docs_client")

CALLBACK_URL = "http://localhost:3030/callback"


class AppianDocsClient:
    """Proxy to the Appian documentation MCP server using OAuth auth."""

    def __init__(self):
        settings = get_settings()
        self.url = settings.appian_docs_url
        self.token = settings.appian_docs_token
        self._storage = FileTokenStorage("appian-docs")

    def _make_oauth_provider(self) -> OAuthClientProvider:
        """Create an OAuth provider that uses stored tokens (no browser popup)."""

        async def _no_browser(url: str) -> None:
            # During normal server operation, we don't open browsers.
            # If this is called, tokens have expired — raise an error.
            raise RuntimeError(
                "OAuth tokens expired. Run `py auth_docs_mcp.py` to re-authenticate."
            )

        async def _no_callback():
            raise RuntimeError("OAuth callback not available in server mode.")

        return OAuthClientProvider(
            server_url=self.url,
            client_metadata=OAuthClientMetadata(
                client_name="Appian AI Copilot Backend",
                redirect_uris=[AnyUrl(CALLBACK_URL)],
            ),
            storage=self._storage,
            redirect_handler=_no_browser,
            callback_handler=_no_callback,
        )

    def _make_http_client(self) -> httpx2.AsyncClient:
        """Create an HTTP client with OAuth auth (uses stored tokens)."""
        oauth = self._make_oauth_provider()
        return httpx2.AsyncClient(auth=oauth, follow_redirects=True, timeout=30.0)

    def _make_http_client_fallback(self) -> httpx2.AsyncClient:
        """Fallback: use raw Bearer token if configured (for API key auth)."""
        headers = {}
        if self.token:
            if self.token.lower().startswith("bearer "):
                headers["Authorization"] = self.token
            else:
                headers["Authorization"] = f"Bearer {self.token}"
        return httpx2.AsyncClient(headers=headers, timeout=30.0)

    async def _connect_and_call(self, tool_name: str, arguments: dict) -> dict:
        """Try OAuth first, fall back to raw token if OAuth storage is empty."""
        logger.info("docs MCP: calling tool=%r arguments=%r", tool_name, arguments)

        # Check if we have OAuth tokens stored
        stored_tokens = await self._storage.get_tokens()

        if stored_tokens:
            # Use OAuth flow (tokens auto-refresh)
            http_client = self._make_http_client()
            logger.debug("docs MCP: authenticating via stored OAuth tokens")
        elif self.token:
            # Fall back to raw Bearer token from .env
            http_client = self._make_http_client_fallback()
            logger.debug("docs MCP: authenticating via configured Bearer token")
        else:
            logger.error("docs MCP: no authentication configured")
            raise RuntimeError(
                "No authentication configured for Docs MCP. "
                "Run `py auth_docs_mcp.py` to authenticate via browser."
            )

        async with streamable_http_client(self.url, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                content_parts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        content_parts.append(content.text)
                    elif hasattr(content, "data"):
                        content_parts.append(str(content.data))
                logger.info(
                    "docs MCP: tool=%r returned isError=%s content_parts=%d",
                    tool_name,
                    result.is_error,
                    len(content_parts),
                )
                return {"content": content_parts, "isError": result.is_error}

    async def list_tools(self) -> list[dict]:
        """Discover available tools on the docs MCP server."""
        stored_tokens = await self._storage.get_tokens()

        if stored_tokens:
            http_client = self._make_http_client()
        elif self.token:
            http_client = self._make_http_client_fallback()
        else:
            raise RuntimeError("No authentication configured for Docs MCP.")

        async with streamable_http_client(self.url, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else None,
                    }
                    for tool in tools_result.tools
                ]

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool on the docs MCP server."""
        return await self._connect_and_call(tool_name, arguments)

    async def search(self, query: str) -> dict:
        """Search Appian documentation."""
        # The kapa.ai tool is named: search_appian_knowledge_sources
        return await self._connect_and_call("search_appian_knowledge_sources", {"query": query})

    async def get_function_docs(self, function_name: str) -> dict:
        """Get documentation for a specific SAIL function."""
        return await self.search(f"Appian SAIL function {function_name} parameters usage examples")

    async def get_component_docs(self, component_name: str) -> dict:
        """Get documentation for a specific SAIL component."""
        return await self.search(f"Appian SAIL component {component_name} parameters usage")

    async def get_best_practices(self, topic: str) -> dict:
        """Get Appian best practices for a topic."""
        return await self.search(f"Appian best practices {topic}")


def get_docs_client() -> AppianDocsClient:
    return AppianDocsClient()
