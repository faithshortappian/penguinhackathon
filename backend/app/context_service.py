"""Service layer that assembles Appian context for AI consumption."""

import asyncio
from app.appian_client import AppianClient, get_appian_client
from app.models import (
    ApplicationContext,
    RecordTypeSummary,
    FieldSummary,
    RelationshipSummary,
    ExpressionRuleSummary,
    InterfaceSummary,
    ConstantSummary,
    IntegrationSummary,
    ProcessModelSummary,
    GroupSummary,
)


class ContextService:
    def __init__(self, client: AppianClient | None = None):
        self.client = client or get_appian_client()

    async def get_full_context(self, app_uuid: str) -> ApplicationContext:
        """Fetch and assemble the full application context."""
        app_data = await self.client.get_application(app_uuid)

        # Fetch all object lists in parallel
        record_types_data, rules_data, interfaces_data, constants_data, integrations_data, pm_data, groups_data = (
            await asyncio.gather(
                self.client.list_objects_in_app(app_uuid, "record-types"),
                self.client.list_objects_in_app(app_uuid, "expression-rules"),
                self.client.list_objects_in_app(app_uuid, "interfaces"),
                self.client.list_objects_in_app(app_uuid, "constants"),
                self.client.list_objects_in_app(app_uuid, "integrations"),
                self.client.list_objects_in_app(app_uuid, "process-models"),
                self.client.list_groups(app_uuid),
            )
        )

        # Enrich record types with fields and relationships
        record_types = await self._enrich_record_types(
            record_types_data.get("items", record_types_data.get("recordTypes", []))
        )

        # Enrich expression rules with details
        rules = await self._enrich_expression_rules(
            rules_data.get("items", rules_data.get("expressionRules", []))
        )

        # Enrich interfaces
        interfaces = await self._enrich_interfaces(
            interfaces_data.get("items", interfaces_data.get("interfaces", []))
        )

        # Map constants
        constants = self._map_constants(
            constants_data.get("items", constants_data.get("constants", []))
        )

        # Map integrations
        integrations = self._map_integrations(
            integrations_data.get("items", integrations_data.get("integrations", []))
        )

        # Map process models
        process_models = self._map_process_models(
            pm_data.get("items", pm_data.get("processModels", []))
        )

        # Map groups
        groups = self._map_groups(
            groups_data.get("items", groups_data.get("groups", []))
        )

        return ApplicationContext(
            uuid=app_uuid,
            name=app_data.get("name", ""),
            description=app_data.get("description"),
            prefix=app_data.get("prefix"),
            record_types=record_types,
            expression_rules=rules,
            interfaces=interfaces,
            constants=constants,
            integrations=integrations,
            process_models=process_models,
            groups=groups,
        )

    async def get_record_types(self, app_uuid: str) -> list[RecordTypeSummary]:
        """Fetch all record types with fields and relationships."""
        data = await self.client.list_objects_in_app(app_uuid, "record-types")
        items = data.get("items", data.get("recordTypes", []))
        return await self._enrich_record_types(items)

    async def get_record_type_detail(self, uuid: str) -> RecordTypeSummary:
        """Fetch a single record type with full detail."""
        rt = await self.client.get_record_type(uuid)
        fields_data = await self.client.list_record_type_fields(uuid)
        rels_data = await self.client.list_record_type_relationships(uuid)

        fields = [
            FieldSummary(
                uuid=f.get("uuid", ""),
                name=f.get("fieldName", ""),
                field_type=f.get("fieldType", ""),
                is_primary_key=f.get("isPrimaryKey", False),
                is_unique=f.get("isUnique", False),
                description=f.get("description"),
            )
            for f in fields_data.get("items", fields_data.get("fields", []))
        ]

        relationships = [
            RelationshipSummary(
                uuid=r.get("uuid", ""),
                name=r.get("relationshipName", ""),
                relationship_type=r.get("relationshipType", ""),
                target_record_type_uuid=r.get("targetRecordTypeUuid", ""),
                target_record_type_name=r.get("targetRecordTypeName"),
            )
            for r in rels_data.get("items", rels_data.get("relationships", []))
        ]

        return RecordTypeSummary(
            uuid=uuid,
            name=rt.get("name", ""),
            plural_name=rt.get("pluralName"),
            description=rt.get("description"),
            fields=fields,
            relationships=relationships,
        )

    async def get_expression_rules(self, app_uuid: str) -> list[ExpressionRuleSummary]:
        """Fetch all expression rules with signatures."""
        data = await self.client.list_objects_in_app(app_uuid, "expression-rules")
        items = data.get("items", data.get("expressionRules", []))
        return await self._enrich_expression_rules(items)

    async def get_interfaces(self, app_uuid: str) -> list[InterfaceSummary]:
        """Fetch all interfaces with inputs."""
        data = await self.client.list_objects_in_app(app_uuid, "interfaces")
        items = data.get("items", data.get("interfaces", []))
        return await self._enrich_interfaces(items)

    async def get_constants(self, app_uuid: str) -> list[ConstantSummary]:
        """Fetch all constants."""
        data = await self.client.list_objects_in_app(app_uuid, "constants")
        items = data.get("items", data.get("constants", []))
        return self._map_constants(items)

    async def get_integrations(self, app_uuid: str) -> list[IntegrationSummary]:
        """Fetch all integrations."""
        data = await self.client.list_objects_in_app(app_uuid, "integrations")
        items = data.get("items", data.get("integrations", []))
        return self._map_integrations(items)

    # ─── Private helpers ────────────────────────────────────────

    async def _enrich_record_types(self, items: list) -> list[RecordTypeSummary]:
        tasks = [self.get_record_type_detail(rt["uuid"]) for rt in items if "uuid" in rt]
        return await asyncio.gather(*tasks)

    async def _enrich_expression_rules(self, items: list) -> list[ExpressionRuleSummary]:
        async def enrich(item):
            detail = await self.client.get_expression_rule(item["uuid"])
            return ExpressionRuleSummary(
                uuid=item["uuid"],
                name=detail.get("name", item.get("name", "")),
                description=detail.get("description"),
                inputs=detail.get("inputs", []),
                expression=detail.get("expression"),
            )

        tasks = [enrich(item) for item in items if "uuid" in item]
        return await asyncio.gather(*tasks)

    async def _enrich_interfaces(self, items: list) -> list[InterfaceSummary]:
        async def enrich(item):
            detail = await self.client.get_interface(item["uuid"])
            return InterfaceSummary(
                uuid=item["uuid"],
                name=detail.get("name", item.get("name", "")),
                description=detail.get("description"),
                inputs=detail.get("inputs", []),
            )

        tasks = [enrich(item) for item in items if "uuid" in item]
        return await asyncio.gather(*tasks)

    def _map_constants(self, items: list) -> list[ConstantSummary]:
        return [
            ConstantSummary(
                uuid=c.get("uuid", ""),
                name=c.get("name", ""),
                constant_type=c.get("type", ""),
                value=str(c.get("value", "")),
                description=c.get("description"),
            )
            for c in items
        ]

    def _map_integrations(self, items: list) -> list[IntegrationSummary]:
        return [
            IntegrationSummary(
                uuid=i.get("uuid", ""),
                name=i.get("name", ""),
                description=i.get("description"),
                connected_system_uuid=i.get("connectedSystemUuid"),
            )
            for i in items
        ]

    def _map_process_models(self, items: list) -> list[ProcessModelSummary]:
        return [
            ProcessModelSummary(
                uuid=pm.get("uuid", ""),
                name=pm.get("name", ""),
                description=pm.get("description"),
                process_variables=pm.get("processVariables", []),
            )
            for pm in items
        ]

    def _map_groups(self, items: list) -> list[GroupSummary]:
        return [
            GroupSummary(
                uuid=g.get("uuid", ""),
                name=g.get("name", ""),
                description=g.get("description"),
            )
            for g in items
        ]
