# Appian AI Copilot

A Chrome browser extension + Python backend that provides AI-powered SAIL code assistance inside Appian's online editors. The AI has full context from Appian documentation (via MCP) and your application's design objects.

## Quick Start

### Prerequisites

- Python 3.10+ (`py --version`)
- Google AI Studio API key ([get one here](https://aistudio.google.com/apikey))
- Chrome browser (for the extension)

### 1. Clone and install

```bash
git clone https://github.com/faithshortappian/penguinhackathon.git
cd penguinhackathon/backend
py -m pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
# Required — your Appian site
APPIAN_BASE_URL=https://your-site.appiancloud.com
APPIAN_API_KEY=your-appian-api-key

# Required — Appian Native MCP (same site, /mcp path)
APPIAN_NATIVE_URL=https://your-site.appiancloud.com/mcp
APPIAN_NATIVE_TOKEN=your-jwt-token

# Required — Appian Docs MCP (authenticated via OAuth, see step 3)
APPIAN_DOCS_URL=https://appian-docs-public.mcp.kapa.ai
APPIAN_DOCS_TOKEN=

# Required — Google Gemini AI
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL=gemini-3.6-flash

# Optional
CACHE_TTL_SECONDS=300
```

### 3. Authenticate with Appian Docs MCP (one-time)

The documentation MCP requires OAuth login via browser:

```bash
cd backend
py auth_docs_mcp.py
```

This opens your browser for Google/GitHub sign-in. After authenticating, tokens are saved to `.tokens/` and reused automatically.

### 4. Start the backend server

```bash
cd backend
py -m uvicorn app.main:app --port 8000
```

Server runs at `http://localhost:8000`. Open `http://localhost:8000/docs` for the Swagger UI.

### 5. Verify it works

```powershell
# Health check
Invoke-RestMethod -Uri "http://localhost:8000/health"

# Test AI endpoint
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ai/process" -Method POST -ContentType "application/json" -Body '{"prompt": "Write a SAIL expression that returns hello world", "code": "", "ruleInputs": []}' | ConvertTo-Json -Depth 5
```

Or with curl (Linux/Mac):

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/api/v1/ai/process \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a SAIL expression that returns hello world", "code": "", "ruleInputs": []}'
```

### 6. Install the Chrome extension

1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select the `frontend/` folder
5. The extension icon appears in your toolbar

The extension connects to `http://localhost:8000` by default. To change this, send a message from the extension's dev console:

```js
chrome.runtime.sendMessage({ type: "SET_BACKEND_URL", url: "http://localhost:8000" });
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ai/process` | Process SAIL code through AI with Appian context |
| POST | `/api/v1/ai/process/validate` | Same + validates output via Native MCP |
| POST | `/api/v1/validate-expression` | Validate expression syntax + references |
| GET | `/api/v1/app/{uuid}/context` | Get full application context |
| GET | `/api/v1/health` | Test all backend connections |
| GET | `/health` | Simple alive check |

### AI Process endpoint

**Request:**
```json
{
  "code": "a!localVariables(local!x: 1, local!x + 1)",
  "prompt": "Add error handling",
  "ruleInputs": [{"name": "inputValue", "type": "Number (Integer)"}],
  "appUuid": "optional-app-uuid"
}
```

**Response:**
```json
{
  "summary": "Added null check before performing arithmetic.",
  "code": "a!localVariables(\n  local!x: ri!inputValue,\n  if(isnull(local!x), 0, local!x + 1)\n)",
  "ruleInputs": [{"name": "inputValue", "type": "Number (Integer)"}]
}
```

## Project Structure

```
penguinhackathon/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings from .env
│   │   ├── ai_routes.py         # POST /api/v1/ai/process
│   │   ├── ai_client.py         # Google Gemini client
│   │   ├── compat_routes.py     # Legacy frontend-compatible routes
│   │   ├── appian_client.py     # Appian Design API client
│   │   ├── native_client.py     # Appian Native MCP client
│   │   ├── docs_client.py       # Appian Docs MCP client (OAuth)
│   │   ├── oauth_storage.py     # Token persistence for OAuth
│   │   ├── context_service.py   # App context orchestration
│   │   ├── models.py            # Pydantic models
│   │   └── health_routes.py     # Connection diagnostics
│   ├── auth_docs_mcp.py         # One-time OAuth login script
│   ├── .env.example
│   ├── requirements.txt
│   └── TEST_CASES.md            # Manual test commands
├── frontend/
│   ├── manifest.json            # Chrome extension manifest
│   ├── background.js            # Service worker
│   ├── content.js               # Injected into Appian pages
│   ├── panel/                   # Side panel UI
│   └── parser/                  # Local SAIL analyzer
└── documentation/
    ├── 01-OVERVIEW.md
    ├── 02-BACKEND.md
    └── 03-DESIGN-DECISIONS.md
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Gemini API error: 404 NOT_FOUND` | Model name wrong. Check `GEMINI_MODEL` in `.env` |
| `Unable to locate credentials` | Wrong LLM provider config. Ensure `GEMINI_API_KEY` is set |
| Docs MCP returns `401`/`403` | Run `py auth_docs_mcp.py` to re-authenticate |
| Appian endpoints unreachable | Need VPN access to your Appian cloud site |
| Port 8000 already in use | Kill existing: `Get-Process python* \| Stop-Process -Force` |
| Extension not connecting | Check backend URL is `http://localhost:8000` in extension settings |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.14, FastAPI, uvicorn |
| AI | Google Gemini 3.6 Flash (Interactions API) |
| MCP | Official Python MCP SDK (streamable HTTP + OAuth) |
| Frontend | Chrome Extension (Manifest V3), vanilla JS |
| Caching | In-memory TTLCache |
