# Design Decisions Log

Tracks all architectural and implementation decisions made during development.

---

## DD-001: Backend Language & Framework

**Date:** 2026-08-10
**Decision:** Python with FastAPI
**Rationale:** Native async support, Pydantic typing, httpx async client, fast to prototype for hackathon.

---

## DD-002: MCP Integration Approach — Option A (Direct HTTP Proxy)

**Date:** 2026-08-10
**Decision:** Option A — Direct HTTP Proxy
**Rationale:** Both target MCP servers have HTTP endpoints. Simpler, fewer deps, faster to build.

**Tradeoffs:** Coupled to HTTP transport, no dynamic discovery at protocol level, can't connect to stdio servers.

---

## DD-003: Caching Strategy

**Date:** 2026-08-10
**Decision:** In-memory TTL cache (cachetools) with 5-minute default TTL.
**Rationale:** Simple, no external infra, reasonable staleness balance.

---

## DD-004: Three-Layer API Design

**Date:** 2026-08-10
**Decision:** Split into `/api/v1/app/...` (context), `/api/v1/dev/...` (native MCP), `/api/v1/docs/...` (docs MCP).
**Rationale:** Clear separation, each layer independently testable and cacheable.

---

## DD-005: CORS Configuration

**Date:** 2026-08-10
**Decision:** Allow all origins (`*`) during development.
**Rationale:** Chrome extensions have unique origins. Lock down to extension ID in production.

---

## DD-006: MCP Client Library (Hybrid Option A + SDK)

**Date:** 2026-08-10
**Context:** Testing revealed both `appian-docs` and `appian-native` MCP servers use Streamable HTTP transport (MCP protocol over SSE), not plain REST. Direct HTTP POST calls get 404s because the protocol requires a session handshake.

**Decision:** Use the official `mcp` Python SDK (`mcp>=2.0.0`) with its `streamable_http_client` transport.

**Rationale:**
- SDK handles SSE transport, session init, and JSON-RPC framing
- Still lightweight (no process management or stdio)
- Only ~3 extra lines per call vs raw HTTP

**Key Findings:**
- `streamable_http_client()` yields a 2-tuple `(read_stream, write_stream)`, not 3
- Auth headers go on a custom `httpx2.AsyncClient` passed as `http_client=`
- Connection errors propagate as `ExceptionGroup` (TaskGroup errors)
- DNS/VPN access required to reach Appian cloud endpoints

---

*Add new decisions below as they are made.*
