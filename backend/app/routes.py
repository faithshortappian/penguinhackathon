"""API routes for the Appian context service."""

from fastapi import APIRouter, HTTPException
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
