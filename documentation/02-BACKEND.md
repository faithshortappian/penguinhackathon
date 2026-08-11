# Backend Implementation

## Running

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env              # fill in credentials
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for interactive Swagger UI.

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point, CORS, router registration
│   ├── config.py            # Pydantic Settings loaded from .env
│   ├── ai_routes.py         # POST /api/v1/ai/process — main integration endpoint
│   ├── ai_client.py         # Amazon Bedrock Converse API client (Claude)
│   ├── appian_client.py     # Direct Appian Design API client (TTL cached)
│   ├── native_client.py     # Appian Native MCP client (MCP SDK, streamable HTTP)
│   ├── docs_client.py       # Appian Docs MCP client (MCP SDK, streamable HTTP)
│   ├── context_service.py   # Orchestrates full app context (parallel fetches)
│   ├── models.py            # Pydantic response models for app context
│   └── health_routes.py     # GET /api/v1/health — connection diagnostics
├── .env.example
├── .env                     # (gitignored) actual credentials
├── .gitignore
└── requirements.txt
```

## Configuration (.env)

| Variable | Purpose |
|----------|---------|
| `APPIAN_BASE_URL` | Appian site URL for Design API |
| `APPIAN_API_KEY` | API key/JWT for Design API |
| `APPIAN_NATIVE_URL` | Appian Native MCP HTTP endpoint |
| `APPIAN_NATIVE_TOKEN` | JWT for Native MCP auth |
| `APPIAN_DOCS_URL` | Appian Docs MCP endpoint |
| `APPIAN_DOCS_TOKEN` | Bearer token for Docs MCP |
| `CACHE_TTL_SECONDS` | Cache TTL in seconds (default 300) |
| `BEDROCK_MODEL_ID` | Amazon Bedrock model ID (default: `anthropic.claude-sonnet-4-20250514`) |
| `BEDROCK_REGION` | AWS region for Bedrock (default: `us-east-1`) |

AWS credentials for Bedrock are resolved via the standard boto3 credential chain (env vars, `~/.aws/credentials`, IAM role).

## Dependencies

| Package | Purpose |
|---------|---------|
| fastapi | Web framework |
| uvicorn | ASGI server |
| httpx | Async HTTP client (Design API) |
| pydantic / pydantic-settings | Data validation + .env loading |
| python-dotenv | .env file support |
| cachetools | TTL cache for Design API |
| mcp | Official MCP Python SDK (streamable HTTP transport) |
| boto3 | AWS SDK for Bedrock AI calls |

## API Endpoints

### AI Processing (`/api/v1/ai/...`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ai/process` | Process SAIL code through AI with full Appian context |
| POST | `/ai/process/validate` | Same as above + validates output via Native MCP |

### Health (`/api/v1/health/...`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Simple health check |
| GET | `/api/v1/health` | Full health — tests all three connections |
| GET | `/api/v1/health/design-api` | Test Appian Design API connectivity |
| GET | `/api/v1/health/native-mcp` | Test Appian Native MCP connectivity |
| GET | `/api/v1/health/docs-mcp` | Test Appian Docs MCP connectivity |

## Script Summaries

### `main.py`
Application entry point. Creates the FastAPI app, configures CORS for the Chrome extension, and registers the health and AI routers. Serves as the startup file for uvicorn.

### `config.py`
Loads all configuration from `.env` using Pydantic Settings. Exposes connection URLs, tokens, cache TTL, and Bedrock model settings as typed properties. Uses `@lru_cache` to ensure a single settings instance.

### `ai_routes.py`
The core integration endpoint. Accepts `{ code, prompt, ruleInputs, appUuid }` from the frontend. Gathers context in parallel from both the Appian Docs MCP (documentation search) and the Design API (record types, rules, constants). Feeds everything into the Bedrock AI and returns `{ summary, code, ruleInputs }`. Also provides a `/process/validate` variant that validates the AI output against the Appian Native MCP.

### `ai_client.py`
Wraps Amazon Bedrock's Converse API. Builds a system prompt enriched with Appian documentation and app context, sends the user's code + prompt + rule inputs, and parses the structured JSON response (summary, code, ruleInputs) from the model.

### `appian_client.py`
Direct HTTP client for the Appian Design API. Fetches applications, record types, fields, relationships, expression rules, interfaces, constants, integrations, process models, and groups. Uses an in-memory TTL cache to avoid redundant API calls.

### `native_client.py`
Client for the Appian Native MCP server using the official MCP Python SDK with streamable HTTP transport. Provides methods for expression validation, testing rules/interfaces, and listing design objects. Used by the AI route to validate generated code.

### `docs_client.py`
Client for the Appian Docs MCP server (hosted by kapa.ai). Searches documentation and retrieves function/component references. Used by the AI route to enrich the LLM prompt with relevant Appian documentation.

### `context_service.py`
Orchestration layer that assembles a complete application context. Fetches record types, expression rules, interfaces, constants, integrations, process models, and groups in parallel via the Design API client, then enriches record types with their fields and relationships.

### `models.py`
Pydantic models representing the application context: `ApplicationContext`, `RecordTypeSummary`, `FieldSummary`, `RelationshipSummary`, `ExpressionRuleSummary`, `InterfaceSummary`, `ConstantSummary`, `IntegrationSummary`, `ProcessModelSummary`, `GroupSummary`.

### `health_routes.py`
Diagnostic endpoints that test connectivity to each backend dependency (Design API, Native MCP, Docs MCP). Returns per-service status and a combined health flag. Essential for debugging network/VPN issues.

## Integration Flow

```
Frontend (Chrome Extension)
    │
    │  POST /api/v1/ai/process
    │  { code, prompt, ruleInputs, appUuid }
    │
    ▼
┌─────────────────────────────────────────────┐
│              ai_routes.py                    │
│                                             │
│  1. _gather_docs_context()                  │
│     └─► Appian Docs MCP (search docs)       │
│                                             │
│  2. _gather_app_context()                   │
│     └─► Design API (record types, rules,    │
│         constants, interfaces)              │
│                                             │
│  3. ai_client.process_expression()          │
│     └─► Amazon Bedrock (Claude)             │
│         System prompt: docs + app context   │
│         User message: code + prompt + inputs│
│                                             │
│  4. Return { summary, code, ruleInputs }    │
└─────────────────────────────────────────────┘
```

---

*Last updated: 2026-08-11*
