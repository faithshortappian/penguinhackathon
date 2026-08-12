"""API routes for AI-powered SAIL code processing.

Accepts code + prompt + rule inputs from the frontend,
enriches with Appian docs and app context via MCP,
processes through Bedrock AI, and returns the result.
"""

import asyncio
import logging
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ai_client import get_ai_client
from app.docs_client import get_docs_client
from app.context_service import ContextService

logger = logging.getLogger("app.ai")

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
        logger.info("docs_context: skipped (empty search query)")
        return ""

    query = search_query.strip()[:200]
    logger.info("docs_context: searching Appian docs for query=%r", query)

    try:
        # Search docs for relevant content
        search_result = await docs_client.search(query)
        if search_result and not search_result.get("isError"):
            for part in search_result.get("content", []):
                context_parts.append(part)
            logger.info(
                "docs_context: found %d result part(s) for query=%r",
                len(context_parts),
                query,
            )
        else:
            logger.warning(
                "docs_context: docs MCP returned an error for query=%r (result=%r)",
                query,
                search_result,
            )
    except Exception:
        logger.exception("docs_context: docs MCP search failed for query=%r", query)

    context = "\n\n".join(context_parts)[:8000]  # Cap context size
    logger.info("docs_context: using %d chars of docs context", len(context))
    return context


async def _gather_app_context(app_uuid: str | None) -> str:
    """Fetch application context (record types, rules, constants).

    Uses the parsed context store (from ZIP upload) as the primary source.
    Falls back to the live Appian Design API if app_uuid is provided and
    no parsed context is available.
    """
    # First: try the parsed context store (richer, offline, no API key needed)
    from app.context_store import is_loaded, get_by_type, get_search_index
    if is_loaded():
        try:
            parts = []
            rules = get_by_type("Expression Rule")
            if rules:
                rules_str = "\n".join(
                    f"  - rule!{r['name']}({', '.join(i.get('name', '') for i in r.get('inputs', [])[:5])})"
                    for r in rules[:30]
                )
                parts.append(f"Expression Rules ({len(rules)} total, showing first 30):\n{rules_str}")

            constants = get_by_type("Constant")
            if constants:
                consts_str = "\n".join(
                    f"  - const!{c['name']} ({c.get('constant_type', '')})"
                    for c in constants[:30]
                )
                parts.append(f"Constants ({len(constants)} total, showing first 30):\n{consts_str}")

            record_types = get_by_type("Record Type")
            if record_types:
                rt_summary = []
                for rt in record_types[:15]:
                    fields = rt.get("fields", [])
                    fields_str = ", ".join(
                        f.get("name", f.get("field_name", "?")) for f in fields[:8]
                    )
                    rt_summary.append(f"  - recordType!{rt['name']}: [{fields_str}]")
                parts.append(f"Record Types ({len(record_types)} total, showing first 15):\n" + "\n".join(rt_summary))

            interfaces = get_by_type("Interface")
            if interfaces:
                ifaces_str = "\n".join(
                    f"  - rule!{i['name']}({', '.join(inp.get('name', '') for inp in i.get('inputs', [])[:3])})"
                    for i in interfaces[:20]
                )
                parts.append(f"Interfaces ({len(interfaces)} total, showing first 20):\n{ifaces_str}")

            context_str = "\n\n".join(parts)[:8000]
            if context_str:
                logger.info("app_context: using parsed context store (%d chars)", len(context_str))
                return context_str
        except Exception as e:
            logger.warning("app_context: parsed context read failed: %s", e)

    # Fallback: live Appian Design API (requires app_uuid + API key)
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


async def _validate_with_docs_mcp(code: str) -> list[str] | None:
    """Sanity-check the functions/components referenced in the code against
    the Appian Docs MCP, flagging any that don't turn up documentation.

    Returns None when the Docs MCP isn't configured/reachable (distinct
    from an empty list, which means it ran and found nothing to flag) so
    callers can tell "not checked" apart from "checked, no issues".
    """
    if not code.strip():
        return None

    functions = sorted(set(re.findall(r'([a-z]![\w]+)', code)))
    if not functions:
        return []

    docs_client = get_docs_client()
    diagnostics = []
    checked_any = False

    for name in functions[:10]:  # cap doc lookups per request
        try:
            result = await docs_client.get_function_docs(name)
        except Exception:
            continue

        checked_any = True
        if not result or result.get("isError"):
            diagnostics.append(f"Could not verify {name} against Appian docs.")
            continue

        content = "\n".join(str(part) for part in result.get("content", []))
        if name not in content:
            diagnostics.append(
                f"{name} was not found in Appian documentation — verify it's a real function/component."
            )

    return diagnostics if checked_any else None


# ─── Main Endpoint ───────────────────────────────────────────────

async def _process(request: ProcessRequest) -> dict:
    """Shared AI-processing step: gather context, call the model, return the
    raw result dict (summary, code, ruleInputs, syntaxWarnings)."""
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

    ai_client = get_ai_client()
    try:
        return await ai_client.process_expression(
            code=request.code,
            prompt=request.prompt,
            rule_inputs=[ri.model_dump() for ri in request.ruleInputs],
            docs_context=docs_context,
            app_context=app_context,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


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
    result = await _process(request)

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
    Same as /process but also validates the AI output: a local, string-aware
    bracket-balance check (see syntax_check.py) that runs unconditionally, and
    — when the Docs MCP is configured and reachable — a check that every
    function/component referenced in the code actually turns up in Appian's
    documentation. Returns the processed result plus a combined `validation`
    list of diagnostics from both.
    """
    result = await _process(request)
    code = result["code"]

    syntax_warnings = [f"[syntax] {w}" for w in result.get("syntaxWarnings", [])]

    docs_result = await _validate_with_docs_mcp(code)
    docs_ran = docs_result is not None
    docs_diagnostics = [f"[docs] {d}" for d in (docs_result or [])]

    return {
        "summary": result["summary"],
        "code": code,
        "ruleInputs": result["ruleInputs"],
        "validation": syntax_warnings + docs_diagnostics,
        "docsValidationRan": docs_ran,
    }
