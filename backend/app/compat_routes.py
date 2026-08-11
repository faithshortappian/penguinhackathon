"""Backward-compatible routes that the frontend extension currently calls.

These endpoints match what background.js expects:
  - POST /api/v1/validate-expression
  - GET  /api/v1/app/{uuid}/context
"""

import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.context_service import ContextService
from app.models import ApplicationContext

router = APIRouter(prefix="/api/v1")
service = ContextService()


# ─── Validate Expression ─────────────────────────────────────────

class ValidateExpressionRequest(BaseModel):
    expression: str
    app_uuid: str | None = None


class ValidationDiagnostic(BaseModel):
    severity: str
    message: str
    line: int | None = None
    column: int | None = None


class ValidateExpressionResponse(BaseModel):
    valid: bool
    diagnostics: list[ValidationDiagnostic] = []


@router.post("/validate-expression", response_model=ValidateExpressionResponse)
async def validate_expression(req: ValidateExpressionRequest):
    """
    Validate a SAIL expression against application context.
    Checks rule!/const!/recordType! references against real objects.
    """
    diagnostics = []

    if req.app_uuid:
        try:
            context = await service.get_full_context(req.app_uuid)

            # Check rule! references
            rule_names = {r.name for r in context.expression_rules}
            for token in _extract_prefixed_refs(req.expression, "rule!"):
                if token not in rule_names:
                    diagnostics.append(ValidationDiagnostic(
                        severity="warning",
                        message=f'Expression rule "{token}" not found in application',
                    ))

            # Check const! references
            const_names = {c.name for c in context.constants}
            for token in _extract_prefixed_refs(req.expression, "const!"):
                if token not in const_names:
                    diagnostics.append(ValidationDiagnostic(
                        severity="warning",
                        message=f'Constant "{token}" not found in application',
                    ))

        except Exception as e:
            diagnostics.append(ValidationDiagnostic(
                severity="info",
                message=f"Could not fetch app context: {str(e)[:100]}",
            ))

    # Basic syntax checks
    diagnostics.extend(_basic_syntax_check(req.expression))

    valid = not any(d.severity == "error" for d in diagnostics)
    return ValidateExpressionResponse(valid=valid, diagnostics=diagnostics)


# ─── Application Context ─────────────────────────────────────────

@router.get("/app/{app_uuid}/context", response_model=ApplicationContext)
async def get_app_context(app_uuid: str):
    """Fetch full application context (record types, rules, constants, etc.)."""
    try:
        return await service.get_full_context(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch app context: {str(e)[:200]}")


# ─── Helpers ─────────────────────────────────────────────────────

def _extract_prefixed_refs(expression: str, prefix: str) -> list[str]:
    """Extract references like rule!myRule or const!MY_CONST from an expression."""
    pattern = re.escape(prefix) + r'([\w]+)'
    return re.findall(pattern, expression)


def _basic_syntax_check(expression: str) -> list[ValidationDiagnostic]:
    """Run basic syntax checks on an expression."""
    diagnostics = []

    # Check balanced parentheses
    depth = 0
    for i, ch in enumerate(expression):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth < 0:
            diagnostics.append(ValidationDiagnostic(
                severity="error",
                message="Unmatched closing parenthesis",
                line=expression[:i].count('\n') + 1,
                column=i - expression[:i].rfind('\n'),
            ))
            break

    if depth > 0:
        diagnostics.append(ValidationDiagnostic(
            severity="error",
            message=f"Unclosed parenthesis ({depth} still open)",
        ))

    # Check for empty expression
    if not expression.strip():
        diagnostics.append(ValidationDiagnostic(
            severity="info",
            message="Expression is empty",
        ))

    return diagnostics
