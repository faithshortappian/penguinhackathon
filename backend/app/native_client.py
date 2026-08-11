"""Client for the Appian Native MCP using the official MCP Python SDK."""

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from app.config import get_settings


class AppianNativeClient:
    """Proxy to the Appian Native MCP server using the MCP SDK."""

    def __init__(self):
        settings = get_settings()
        self.url = settings.appian_native_url
        self.token = settings.appian_native_token

    def _make_http_client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=60.0,
        )

    async def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool on the native server."""
        async with streamable_http_client(
            self.url, http_client=self._make_http_client()
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                content_parts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        content_parts.append(content.text)
                    elif hasattr(content, "data"):
                        content_parts.append(str(content.data))
                return {"content": content_parts, "isError": result.isError}

    async def list_tools(self) -> list[dict]:
        """Discover available tools on the native MCP server."""
        async with streamable_http_client(
            self.url, http_client=self._make_http_client()
        ) as (read_stream, write_stream):
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

    # ─── Convenience methods ────────────────────────────────────

    async def validate_expression(self, expression: str) -> dict:
        return await self._call_tool("validateExpression", {"expression": expression})

    async def get_record_type(self, uuid: str) -> dict:
        return await self._call_tool("getRecordType", {"uuid": uuid})

    async def list_record_types(self, app_uuid: str | None = None) -> dict:
        args = {}
        if app_uuid:
            args["appUuid"] = app_uuid
        return await self._call_tool("listRecordTypes", args)

    async def get_expression_rule(self, uuid: str) -> dict:
        return await self._call_tool("getExpressionRule", {"uuid": uuid})

    async def list_expression_rules(self, app_uuid: str | None = None) -> dict:
        args = {}
        if app_uuid:
            args["appUuid"] = app_uuid
        return await self._call_tool("listExpressionRules", args)

    async def get_interface(self, uuid: str) -> dict:
        return await self._call_tool("getInterface", {"uuid": uuid})

    async def list_interfaces(self, app_uuid: str | None = None) -> dict:
        args = {}
        if app_uuid:
            args["appUuid"] = app_uuid
        return await self._call_tool("listInterfaces", args)

    async def get_constant(self, uuid: str) -> dict:
        return await self._call_tool("getConstant", {"uuid": uuid})

    async def list_constants(self, app_uuid: str | None = None) -> dict:
        args = {}
        if app_uuid:
            args["appUuid"] = app_uuid
        return await self._call_tool("listConstants", args)

    async def test_expression_rule(self, uuid: str, inputs: dict | None = None) -> dict:
        args = {"uuid": uuid, "type": "EXPRESSION_RULE"}
        if inputs:
            args["inputs"] = inputs
        return await self._call_tool("testRule", args)

    async def test_interface(self, uuid: str, inputs: dict | None = None) -> dict:
        args = {"uuid": uuid}
        if inputs:
            args["inputs"] = inputs
        return await self._call_tool("testInterface", args)


def get_native_client() -> AppianNativeClient:
    return AppianNativeClient()
