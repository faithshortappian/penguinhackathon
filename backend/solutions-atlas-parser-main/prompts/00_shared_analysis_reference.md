# Shared Analysis Reference

This document is referenced by all bundle-type prompts. You do NOT need to paste this separately — each prompt is self-contained. This exists only as a maintenance reference.

## Bundle JSON Structure

Every bundle JSON contains:

```
{
  "_metadata": { "bundle_type", "root_object", "total_objects" },
  "entry_point": { type-specific details },
  "objects": {
    "expression_rules": [{ "name", "description", "data": { "sail_code", "inputs" }, "calls", "called_by" }],
    "interfaces": [{ "name", "data": { "sail_code", "parameters" }, "calls", "called_by" }],
    "processes": [{ "name", "data": { "nodes", "variables", "flows" }, "calls", "called_by" }],
    "record_types": [{ "name", "data": { "fields", "relationships", "actions", "views" } }],
    "integrations": [{ "name", "data": { "http_method", "url", "connected_system_name" } }],
    "constants": [{ "name", "data": { "value", "type" } }]
  }
}
```

## SAIL Code Reading Guide

- `rule!Name(...)` — calls an expression rule
- `cons!Name` — references a constant
- `a!textField(label: "X")` — text input field
- `a!dropdownField(...)` — dropdown selector
- `a!gridField(...)` / `a!recordGrid(...)` — data grid/table
- `a!buttonWidget(label: "X", ...)` — clickable button
- `a!queryRecordType(...)` — database query
- `if(condition, trueVal, falseVal)` — conditional logic
- `a!forEach(items: ..., expression: ...)` — loop over items
- `a!save(target, value)` — save data to variable
- `ri!paramName` — rule input (parameter)
- `local!varName` — local variable

## Object Analysis Rules

**Process Models**: Read `data.nodes[]` — each node is a workflow step. Gateway nodes have `gateway_conditions[].condition` (decision rules). User Input nodes have `form_expression` (form shown). Subprocess nodes have `subprocess_uuid`.

**Interfaces**: Read `data.sail_code` — the UI definition. Identify form fields, grids, buttons, conditional visibility.

**Expression Rules**: Read `data.sail_code` — business logic. Focus on rules with many `called_by` entries (core shared logic).

**Record Types**: Read `data.fields[]` for data structure, `data.relationships[]` for entity connections.

**Integrations**: Read `data.http_method`, `data.url`, `data.connected_system_name`.

**Constants**: Read `data.value` for configuration values.

## Output Format

Every summary `.md` file must follow this structure:

```markdown
# [Bundle Name]

## Overview
2-3 sentences: what this does, who uses it, what business purpose it serves.

## Entry Point
- Type: [action/process/page/site/web_api]
- [Type-specific details]

## Business Logic Flow
Step-by-step walkthrough in plain business language:
1. [Step — what happens, what data is involved]
2. [Decision point — translate condition to business rule]
3. ...

## Data Model
Record types involved:
- **[RecordType]**: [business meaning, key fields used]

## Business Rules
1. [Rule in plain English — e.g., "Evaluation can only be started when status is Draft"]

## User Interactions
- **[Screen Name]**: [what it shows, what data is collected, what actions are available]

## External Integrations
(only if integrations exist)
- **[Integration]**: [METHOD] [URL] via [Connected System] — [purpose]

## Key Dependencies
- Total objects: [N]
- Breakdown: [N] expression rules, [N] interfaces, etc.
- Most-used: [top 3-5 by called_by count]
```

## Guidelines

- Write for a business analyst — NO raw SAIL code in output
- Be specific — use actual field names, record type names, condition values
- Infer purpose from object names when descriptions are empty
- Gateway conditions → business decision rules
- Interface SAIL → screen descriptions
- Large bundles (100+ objects): focus on entry point's direct `calls` and top 10 most-connected objects
- Small bundles (<30 objects): describe every object
- Each summary must be self-contained
