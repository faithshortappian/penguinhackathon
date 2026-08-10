"""Response models for the context API."""

from pydantic import BaseModel


class FieldSummary(BaseModel):
    uuid: str
    name: str
    field_type: str
    is_primary_key: bool = False
    is_unique: bool = False
    description: str | None = None


class RelationshipSummary(BaseModel):
    uuid: str
    name: str
    relationship_type: str
    target_record_type_uuid: str
    target_record_type_name: str | None = None


class RecordTypeSummary(BaseModel):
    uuid: str
    name: str
    plural_name: str | None = None
    description: str | None = None
    fields: list[FieldSummary] = []
    relationships: list[RelationshipSummary] = []


class ExpressionRuleSummary(BaseModel):
    uuid: str
    name: str
    description: str | None = None
    inputs: list[dict] = []
    expression: str | None = None


class InterfaceSummary(BaseModel):
    uuid: str
    name: str
    description: str | None = None
    inputs: list[dict] = []


class ConstantSummary(BaseModel):
    uuid: str
    name: str
    constant_type: str
    value: str | None = None
    description: str | None = None


class IntegrationSummary(BaseModel):
    uuid: str
    name: str
    description: str | None = None
    connected_system_uuid: str | None = None


class ProcessModelSummary(BaseModel):
    uuid: str
    name: str
    description: str | None = None
    process_variables: list[dict] = []


class GroupSummary(BaseModel):
    uuid: str
    name: str
    description: str | None = None


class ApplicationContext(BaseModel):
    """Full application context for AI consumption."""
    uuid: str
    name: str
    description: str | None = None
    prefix: str | None = None
    record_types: list[RecordTypeSummary] = []
    expression_rules: list[ExpressionRuleSummary] = []
    interfaces: list[InterfaceSummary] = []
    constants: list[ConstantSummary] = []
    integrations: list[IntegrationSummary] = []
    process_models: list[ProcessModelSummary] = []
    groups: list[GroupSummary] = []
