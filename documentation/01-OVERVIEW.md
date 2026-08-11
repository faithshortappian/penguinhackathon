# Appian AI Copilot — Full Implementation Overview

## Project Summary

A Chrome browser extension that provides inline AI-powered code assistance within Appian's online code editors (Interface Builder, Expression Rule Editor). The system gives the AI full context about the user's Appian application so suggestions are accurate, contextual, and syntactically valid.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Chrome Extension (Frontend)                    │
│  - Injects into Appian editor pages                             │
│  - Detects cursor position & current expression                 │
│  - Sends context to backend for AI suggestions                  │
│  - Renders inline suggestions (ghost text, popups)              │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP (REST)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI / Python)                    │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Context API │  │  Dev Proxy   │  │    Docs Proxy          │ │
│  │ (Design API)│  │ (Native MCP) │  │    (Docs MCP)          │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────────┘ │
└─────────┼────────────────┼──────────────────────┼───────────────┘
          │                │                      │
          ▼                ▼                      ▼
┌──────────────┐  ┌──────────────────┐  ┌─────────────────────┐
│ Appian       │  │ Appian Native    │  │ Appian Docs MCP     │
│ Design API   │  │ MCP (HTTP/SSE)   │  │ (kapa.ai hosted)    │
└──────────────┘  └──────────────────┘  └─────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Extension | JavaScript/TypeScript, Chrome Manifest V3 |
| Backend | Python 3.14, FastAPI, MCP SDK, httpx, pydantic |
| Caching | In-memory TTLCache (cachetools) |
| MCP Transport | Streamable HTTP (via official `mcp` Python SDK) |

## Status

- [x] Backend scaffolded with all three proxy layers
- [x] MCP SDK integration working (correct transport, auth, unpacking)
- [x] Server starts and health check responds
- [ ] Network connectivity to Appian cloud (VPN/DNS dependent)
- [ ] Chrome extension (frontend)
- [ ] AI completion endpoint
- [ ] End-to-end flow
