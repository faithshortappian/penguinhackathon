"""API routes for the Appian context service."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.context_service import ContextService
from app.models import (
    ApplicationContext,
    RecordTypeSummary,
    ExpressionRuleSummary,
    InterfaceSummary,
    ConstantSummary,
    IntegrationSummary,
)

router = APIRouter(prefix="/api/v1")
service = ContextService()


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
                message=f"Could not fetch app context: {str(e)}",
            ))

    return ValidateExpressionResponse(
        valid=len([d for d in diagnostics if d.severity == "error"]) == 0,
        diagnostics=diagnostics,
    )


def _extract_prefixed_refs(expression: str, prefix: str) -> list[str]:
    """Extract all references with a given prefix from an expression string."""
    refs = []
    search_from = 0
    while True:
        idx = expression.find(prefix, search_from)
        if idx == -1:
            break
        start = idx + len(prefix)
        end = start
        while end < len(expression) and (expression[end].isalnum() or expression[end] == "_"):
            end += 1
        if end > start:
            refs.append(expression[start:end])
        search_from = end
    return refs


@router.get("/app/{app_uuid}/context", response_model=ApplicationContext)
async def get_full_context(app_uuid: str):
    """Get the full application context for AI consumption."""
    try:
        return await service.get_full_context(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/app/{app_uuid}/record-types", response_model=list[RecordTypeSummary])
async def get_record_types(app_uuid: str):
    """Get all record types with fields and relationships."""
    try:
        return await service.get_record_types(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/record-type/{uuid}", response_model=RecordTypeSummary)
async def get_record_type_detail(uuid: str):
    """Get a single record type with full detail."""
    try:
        return await service.get_record_type_detail(uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/app/{app_uuid}/expression-rules", response_model=list[ExpressionRuleSummary])
async def get_expression_rules(app_uuid: str):
    """Get all expression rules with inputs and bodies."""
    try:
        return await service.get_expression_rules(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/app/{app_uuid}/interfaces", response_model=list[InterfaceSummary])
async def get_interfaces(app_uuid: str):
    """Get all interfaces with inputs."""
    try:
        return await service.get_interfaces(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/app/{app_uuid}/constants", response_model=list[ConstantSummary])
async def get_constants(app_uuid: str):
    """Get all constants in the application."""
    try:
        return await service.get_constants(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/app/{app_uuid}/integrations", response_model=list[IntegrationSummary])
async def get_integrations(app_uuid: str):
    """Get all integrations in the application."""
    try:
        return await service.get_integrations(app_uuid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
