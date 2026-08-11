"""API routes for AI-powered SAIL code processing.

Accepts code + prompt + rule inputs from the frontend,
enriches with Appian docs and app context via MCP,
processes through Bedrock AI, and returns the result.
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ai_client import get_ai_client
from app.docs_client import get_docs_client
from app.native_client import get_native_client
from app.context_service import ContextService

router = APIRouter(prefix="/api/v1/ai")
context_service = ContextService()


# ─── Request / Response Models ───────────────────────────────────

class RuleInput(BaseModel):
    name: str
    type: str


class ProcessRequest(BaseModel):
    """Incoming request from the frontend."""
    code: str = ""
    prompt: str = ""
    ruleInputs: list[RuleInput] = []
    appUuid: str | None = None


class ProcessResponse(BaseModel):
    """Response sent back to the frontend."""
    summary: str
    code: str
    ruleInputs: list[RuleInput]


# ─── Helper Functions ────────────────────────────────────────────

async def _gather_docs_context(code: str, prompt: str) -> str:
    """Query the Appian Docs MCP for relevant documentation based on the code/prompt."""
    docs_client = get_docs_client()
    context_parts = []

    # Build a search query from the prompt and code keywords
    search_query = prompt if prompt else ""
    if code:
        # Extract function names from the code for doc lookups
        import re
        functions = re.findall(r'([a-z]![\w]+)', code)
        if functions:
            search_query += " " + " ".join(functions[:5])  # Limit to 5

    if not search_query.strip():
        return ""

    try:
        # Search docs for relevant content
        search_result = await docs_client.search(search_query.strip()[:200])
        if search_result and not search_result.get("isError"):
            for part in search_result.get("content", []):
                context_parts.append(part)
    except Exception:
        pass  # Non-critical — proceed without docs if MCP is unavailable

    return "\n\n".join(context_parts)[:8000]  # Cap context size


async def _gather_app_context(app_uuid: str | None) -> str:
    """Fetch application context (record types, rules, constants) if app UUID provided."""
    if not app_uuid:
        return ""

    try:
        context = await context_service.get_full_context(app_uuid)
        # Serialize to a concise representation for the AI
        parts = []

        if context.record_types:
            rt_summary = []
            for rt in context.record_types:
                fields_str = ", ".join(f"{f.name}({f.field_type})" for f in rt.fields[:10])
                rt_summary.append(f"  - {rt.name}: [{fields_str}]")
            parts.append("Record Types:\n" + "\n".join(rt_summary))

        if context.expression_rules:
            rules_str = "\n".join(
                f"  - rule!{r.name}({', '.join(i.get('name', '') for i in r.inputs)})"
                for r in context.expression_rules[:20]
            )
            parts.append(f"Expression Rules:\n{rules_str}")

        if context.constants:
            consts_str = "\n".join(
                f"  - const!{c.name} ({c.constant_type})"
                for c in context.constants[:20]
            )
            parts.append(f"Constants:\n{consts_str}")

        if context.interfaces:
            ifaces_str = "\n".join(
                f"  - {i.name}({', '.join(inp.get('name', '') for inp in i.inputs)})"
                for i in context.interfaces[:20]
            )
            parts.append(f"Interfaces:\n{ifaces_str}")

        return "\n\n".join(parts)[:6000]  # Cap context size

    except Exception:
        return ""  # Non-critical — proceed without app context


async def _validate_with_native_mcp(code: str) -> str:
    """Optionally validate the code using the Appian Native MCP."""
    if not code.strip():
        return ""

    try:
        native_client = get_native_client()
        result = await native_client.validate_expression(code)
        if result and not result.get("isError"):
            return json.dumps(result.get("content", []))
    except Exception:
        pass

    return ""


# ─── Main Endpoint ───────────────────────────────────────────────

@router.post("/process", response_model=ProcessResponse)
async def process_expression(request: ProcessRequest):
    """
    Process a SAIL expression through AI with full Appian context.

    Flow:
    1. Gather documentation context from Appian Docs MCP
    2. Gather application context (record types, rules, constants)
    3. Send code + prompt + context to Bedrock AI
    4. Return processed result (summary, code, ruleInputs)
    """
    # Gather context in parallel (with timeouts so MCP issues don't block the AI call)
    try:
        docs_context, app_context = await asyncio.wait_for(
            asyncio.gather(
                _gather_docs_context(request.code, request.prompt),
                _gather_app_context(request.appUuid),
            ),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        docs_context = ""
        app_context = ""

    # Process through AI
    ai_client = get_ai_client()
    try:
        result = await ai_client.process_expression(
            code=request.code,
            prompt=request.prompt,
            rule_inputs=[ri.model_dump() for ri in request.ruleInputs],
            docs_context=docs_context,
            app_context=app_context,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Map response back to typed model
    return ProcessResponse(
        summary=result["summary"],
        code=result["code"],
        ruleInputs=[
            RuleInput(name=ri.get("name", ""), type=ri.get("type", "Text"))
            for ri in result["ruleInputs"]
        ],
    )


@router.post("/process/validate", response_model=dict)
async def process_and_validate(request: ProcessRequest):
    """
    Same as /process but also validates the AI output against Appian Native MCP.
    Returns the processed result plus validation diagnostics.
    """
    # First, process through AI
    process_response = await process_expression(request)

    # Then validate the generated code
    validation = await _validate_with_native_mcp(process_response.code)

    return {
        "summary": process_response.summary,
        "code": process_response.code,
        "ruleInputs": [ri.model_dump() for ri in process_response.ruleInputs],
        "validation": json.loads(validation) if validation else None,
    }
