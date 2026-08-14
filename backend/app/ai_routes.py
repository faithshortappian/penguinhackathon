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
from app.config import get_settings

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
    """Query the Appian Docs MCP for relevant documentation based on the code/prompt.

    Runs two kinds of lookups in parallel:
    - one broad search grounded in the user's prompt/intent
    - one dedicated per-function/component lookup for each a!/rule!/etc.
      reference in the code

    The per-component lookups matter because a blended search query dilutes
    component-specific detail (e.g. the exact accepted values for a
    a!buttonWidget's `style` parameter) into a single generic result. Without
    a dedicated lookup, that detail often doesn't make it into context at
    all, and the model falls back on outdated training knowledge — which is
    how stale enum values (e.g. "PRIMARY" instead of the current "SOLID")
    end up in generated code despite the docs-grounding instructions.
    """
    docs_client = get_docs_client()
    context_parts = []

    functions = list(dict.fromkeys(re.findall(r'([a-z]![\w]+)', code))) if code else []

    search_query = (prompt or "").strip()
    if functions:
        search_query += " " + " ".join(functions[:5])
    search_query = search_query.strip()[:200]

    lookups: list[tuple[str, "asyncio.Future"]] = []
    if search_query:
        lookups.append(("search", docs_client.search(search_query)))
    for name in functions[:8]:  # cap dedicated lookups per request
        lookups.append((name, docs_client.get_function_docs(name)))

    # Always pull Appian's SAIL design-inspiration/best-practices guidance
    # (layout, visual hierarchy, component choice, accessibility) as its own
    # dedicated lookup, same reasoning as the per-component lookups above: a
    # blended search query dilutes it into a generic result and the model
    # falls back on generic web-design instincts instead of Appian's actual
    # design guidance.
    lookups.append(
        ("design_best_practices", docs_client.get_best_practices("SAIL interface design inspiration and best practices"))
    )

    logger.info(
        "docs_context: running %d lookup(s) (search=%r, components=%s)",
        len(lookups), search_query, functions[:8],
    )

    results = await asyncio.gather(*(coro for _, coro in lookups), return_exceptions=True)

    for (label, _), result in zip(lookups, results):
        if isinstance(result, BaseException):
            logger.warning("docs_context: lookup %r failed: %s", label, result)
            continue
        if result and not result.get("isError"):
            for part in result.get("content", []):
                context_parts.append(part)
        else:
            logger.warning(
                "docs_context: docs MCP returned an error for lookup=%r (result=%r)",
                label, result,
            )

    max_chars = get_settings().docs_context_max_chars
    context = "\n\n".join(context_parts)[:max_chars]  # Cap context size
    logger.info(
        "docs_context: using %d chars of docs context from %d/%d successful lookup(s)",
        len(context), len(context_parts), len(lookups),
    )
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

        max_chars = get_settings().app_context_max_chars
        return "\n\n".join(parts)[:max_chars]  # Cap context size

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
