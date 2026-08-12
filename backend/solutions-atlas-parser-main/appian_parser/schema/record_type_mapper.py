"""Post-processing: build record_type_map.json and field_map.json by cross-referencing
parsed record type objects with DDL schema tables."""

from typing import Any


def build_record_type_map(parsed_objects: list, schema_result: Any) -> dict:
    """Build mapping from DDL table names to record type UUIDs and relationships.

    Matches by comparing the record type's PK source_field_name to the DDL table's PK column.

    Returns:
        {
            "AS_GSS_EVALUATION": {
                "record_type_uuid": "e6bc8561-...",
                "record_type_name": "AS_GSS_Evaluation_SYNCEDRECORD",
                "relationships": {"vendor": "b6081510-...", ...}
            }
        }
    """
    # Build PK lookup from schema: {pk_column_name: table_name}
    table_pks = {}
    for table_name, table in schema_result.tables.items():
        if table.primary_key:
            table_pks[table.primary_key[0]] = table_name

    # Build record type index: find PK field's source_field_name for each record type
    rt_map = {}
    for obj in parsed_objects:
        if obj.object_type != 'Record Type':
            continue
        data = obj.data
        fields = data.get('fields', [])
        if not fields:
            continue

        # Find the PK field
        pk_source = None
        for f in fields:
            if f.get('is_record_id'):
                pk_source = f.get('source_field_name')
                break

        if not pk_source:
            continue

        # Match to DDL table by PK column name
        table_name = table_pks.get(pk_source)
        if not table_name:
            continue

        # Build relationships map
        relationships = {}
        for rel in data.get('relationships', []):
            rel_name = rel.get('relationship_name')
            target_uuid = rel.get('target_record_type_uuid')
            if rel_name and target_uuid:
                relationships[rel_name] = target_uuid

        rt_map[table_name] = {
            "record_type_uuid": obj.uuid,
            "record_type_name": obj.name,
            "relationships": relationships,
        }

    return rt_map


def build_field_map(parsed_objects: list, schema_result: Any) -> dict:
    """Build mapping from DDL column names to Appian camelCase field names per table.

    Returns:
        {
            "AS_GSS_EVALUATION": {
                "EVALUATION_ID": "evaluationId",
                "EVALUATION_TITLE": "evaluationTitle",
                ...
            }
        }
    """
    # First build record_type_map to know which RT matches which table
    table_pks = {}
    for table_name, table in schema_result.tables.items():
        if table.primary_key:
            table_pks[table.primary_key[0]] = table_name

    field_map = {}
    for obj in parsed_objects:
        if obj.object_type != 'Record Type':
            continue
        data = obj.data
        fields = data.get('fields', [])
        if not fields:
            continue

        # Find table match via PK
        pk_source = None
        for f in fields:
            if f.get('is_record_id'):
                pk_source = f.get('source_field_name')
                break

        if not pk_source:
            continue

        table_name = table_pks.get(pk_source)
        if not table_name:
            continue

        # Build column → field name mapping
        col_map = {}
        for f in fields:
            source = f.get('source_field_name')
            field_name = f.get('field_name')
            if source and field_name:
                col_map[source] = field_name

        if col_map:
            field_map[table_name] = col_map

    return field_map


def build_reference_data_metadata(schema_result: Any, record_type_map: dict) -> dict:
    """Build slim reference data metadata (no row data).

    Returns:
        {
            "AS_GSS_R_DATA": {
                "record_type_uuid": "c34b12a0-...",
                "row_count": 110,
                "ref_types": ["Evaluation Status", "Evaluation Method", ...],
                "key_columns": ["REF_DATA_ID", "REF_LABEL", "REF_TYPE"]
            }
        }
    """
    metadata = {}
    for table_name, rows in schema_result.reference_data.items():
        # Get record type UUID if available
        rt_info = record_type_map.get(table_name, {})
        rt_uuid = rt_info.get("record_type_uuid")

        # Extract unique REF_TYPE values if the table has that column
        ref_types = sorted(set(
            row.get("REF_TYPE") for row in rows
            if row.get("REF_TYPE")
        )) if rows else []

        # Identify key columns (columns present in first row)
        key_columns = list(rows[0].keys()) if rows else []

        metadata[table_name] = {
            "record_type_uuid": rt_uuid,
            "row_count": len(rows),
            "ref_types": ref_types,
            "key_columns": key_columns,
        }

    return metadata
