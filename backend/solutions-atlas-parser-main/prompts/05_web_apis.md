# Generate Summaries — Web APIs (4 bundles)

I need you to generate business-logic summary documents for all **web_api** bundles in an Appian application.

Bundles directory: `OUTPUT_DIR/bundles/`

## Instructions

1. Read `OUTPUT_DIR/bundles/_index.json`
2. Filter to entries where `bundle_type` is `"web_api"`
3. For each web_api bundle:
   a. Read the JSON file at `OUTPUT_DIR/bundles/{entry.file}`
   b. Analyze it using the rules below
   c. Write a summary markdown file at the same path but with `.md` extension (e.g., `web_apis/My_API.json` → `web_apis/My_API.md`)
4. After all are done, print how many summaries were written

## How to Analyze Web API Bundles

A web_api bundle represents an **API endpoint** — an HTTP endpoint exposed by the Appian application for external systems to call.

### Entry Point Structure
```json
{
  "name": "API Name",
  "url_alias": "/api-path",
  "http_method": "GET|POST|PUT|DELETE"
}
```

### Analysis Flow
1. **Endpoint definition**: What's the HTTP method and URL? What does this API do?
2. **Read the SAIL code**: Find the web API in `objects.web_apis[]` if present, or check `objects.expression_rules[]` for the main logic. The SAIL code handles the request/response
3. **Request handling**: What parameters does it expect? What validation is performed?
4. **Business logic**: What expression rules are called? What data is queried or modified?
5. **Response**: What does it return? What error cases are handled?
6. **Integrations**: Does this API call external systems (outbound integrations)?

### Output Format

```markdown
# [API Name]

## Overview
2-3 sentences: what this API does, what external system calls it, what data it exchanges.

## Entry Point
- Type: web_api
- Method: [GET/POST/PUT/DELETE]
- URL: /[url_alias]
- Security: [authentication/authorization if detectable]

## Request
- **Parameters**: [expected inputs — query params, path params, request body fields]
- **Validation**: [input validation rules]

## Business Logic Flow
1. [Request received — what parameters are extracted]
2. [Validation — what checks are performed]
3. [Data operations — what's queried, created, updated]
4. [Response — what's returned]
5. [Error handling — what error responses are possible]

## Data Model
- **[RecordType]**: [how it's read/written by this API]

## Business Rules
1. [Validation rules]
2. [Authorization rules]
3. [Business logic rules]

## External Integrations
(only if outbound integrations exist)
- **[Integration]**: [METHOD] [URL] — [purpose]

## Key Dependencies
- Total objects: [N]
- Breakdown by type
- Most-used shared rules: [top 3-5 by called_by count]
```

## SAIL Reading Guide

- `rule!Name(...)` — calls expression rule | `cons!Name` — constant reference
- `a!httpResponse(statusCode, headers, body)` — HTTP response
- `a!queryRecordType(...)` — database query
- `if(cond, true, false)` — conditional | `ri!param` — rule input
- `a!toJson(...)` — serialize to JSON | `a!fromJson(...)` — parse JSON

## Guidelines

- Write for a business analyst — NO raw SAIL code in output
- Describe the API as an integration point — what it receives, processes, and returns
- Be specific about data fields and validation rules
- Each summary must be self-contained

Start now. Read the `_index.json` first.
