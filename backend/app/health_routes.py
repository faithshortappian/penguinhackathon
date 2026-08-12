"""Health check routes that test each backend connection individually."""

import httpx
import httpx2
from fastapi import APIRouter
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from app.config import get_settings

router = APIRouter(prefix="/api/v1/health")


@router.get("")
async def full_health():
    """Test all connections and report status of each."""
    results = {
        "design_api": await _check_design_api(),
        "docs_mcp": await _check_docs_mcp(),
    }
    results["all_healthy"] = all(r["ok"] for r in results.values())
    return results


@router.get("/design-api")
async def check_design_api():
    """Test connection to Appian Design API (direct REST)."""
    return await _check_design_api()


@router.get("/docs-mcp")
async def check_docs_mcp():
    """Test connection to Appian Docs MCP (streamable HTTP)."""
    return await _check_docs_mcp()


# ─── Internal check functions ───────────────────────────────────

async def _check_design_api() -> dict:
    """Check: Can we reach the Appian Design API?"""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.appian_base_url.rstrip('/')}/design/v1/applications",
                headers={
                    "Appian-API-Key": settings.appian_api_key,
                    "Content-Type": "application/json",
                },
                params={"limit": 1},
            )
            if resp.status_code == 200:
                return {"ok": True, "status": resp.status_code, "message": "Connected"}
            else:
                return {"ok": False, "status": resp.status_code, "message": resp.text[:200]}
    except httpx.ConnectError as e:
        return {"ok": False, "status": None, "message": f"DNS/Network error: {e}"}
    except Exception as e:
        return {"ok": False, "status": None, "message": f"{type(e).__name__}: {e}"}


async def _check_docs_mcp() -> dict:
    """Check: Can we connect to the Appian Docs MCP and list tools?"""
    settings = get_settings()
    try:
        headers = {}
        if settings.appian_docs_token:
            headers["Authorization"] = f"Bearer {settings.appian_docs_token}"
        client = httpx2.AsyncClient(headers=headers, timeout=15.0)
        async with streamable_http_client(settings.appian_docs_url, http_client=client) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = await session.list_tools()
                return {
                    "ok": True,
                    "message": f"Connected — {len(tools.tools)} tools available",
                    "tool_count": len(tools.tools),
                    "sample_tools": [t.name for t in tools.tools[:5]],
                }
    except BaseException as e:
        real_error = e
        if hasattr(e, "exceptions") and e.exceptions:
            real_error = e.exceptions[0]
        return {"ok": False, "message": f"{type(real_error).__name__}: {real_error}"}
