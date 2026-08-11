# Generate Summaries — Actions (57 bundles)

I need you to generate business-logic summary documents for all **action** bundles in an Appian application.

Bundles directory: /Users/ramaswamy.u/repo/appian-parser/web/uploads/1/output/bundles/actions

## Instructions

1. Read `OUTPUT_DIR/bundles/_index.json`
2. Filter to entries where `bundle_type` is `"action"`
3. For each action bundle:
   a. Read the JSON file at `OUTPUT_DIR/bundles/{entry.file}`
   b. Analyze it using the rules below
   c. Write a summary markdown file at the same path but with `.md` extension (e.g., `actions/My_Action.json` → `actions/My_Action.md`)
4. After all are done, print how many summaries were written

## How to Analyze Action Bundles

An action bundle represents a **record type action** — a button/link on a record that triggers a process model.

### Entry Point Structure
```json
{
  "name": "Action Name",
  "record_type": "RecordType that owns this action",
  "process_model": "Process model that gets launched",
  "expressions": {
    "TITLE": "display title expression",
    "DESCRIPTION": "description expression",
    "VISIBILITY": "who can see this action",
    "CONTEXT": "what record data is passed"
  }
}
```

### Analysis Flow
1. **Start with the action trigger**: What record type does this action belong to? What's the visibility condition (who can use it)?
2. **Read the CONTEXT expression**: What record data is passed to the process?
3. **Follow the process model**: Find it in `objects.processes[]`. Walk through `data.nodes[]` in order:
   - Start Event → first activity
   - Gateway nodes: translate `gateway_conditions[].condition` to business decisions
   - User Input nodes: describe the form from `form_expression`
   - Subprocess nodes: note what sub-process is called
   - End Events: what's the outcome?
4. **Trace expression rules**: For rules called by the process or its forms, read their `data.sail_code` to understand the business logic
5. **Identify record types**: What data entities are read/written in this flow?

### Output Format

```markdown
# [Action Name]

## Overview
2-3 sentences: what this action does, which record type it belongs to, what business outcome it produces.

## Entry Point
- Type: action
- Record Type: [X]
- Triggers Process: [Y]
- Visibility: [who can see/use this action — translate the VISIBILITY expression]

## Business Logic Flow
Step-by-step from action trigger to completion:
1. User clicks "[Action Title]" on a [RecordType] record
2. [What data is passed from the record to the process — from CONTEXT expression]
3. [First process step]
4. [Decision point — translate gateway condition to business rule]
5. [User sees form — describe what's on it]
6. [Next steps...]
7. [Outcome — what changes when the process completes]

## Data Model
- **[RecordType]**: [role in this flow, key fields used]
- ...

## Business Rules
1. [Visibility rule — when is this action available]
2. [Validation rules from forms]
3. [Decision rules from gateways]
4. [Business logic from expression rules]

## User Interactions
- **[Form Name]**: [fields shown, data collected, buttons available]

## External Integrations
(only if integrations exist)
- **[Integration]**: [METHOD] [URL] — [purpose]

## Key Dependencies
- Total objects: [N]
- Breakdown by type
- Most-used shared rules: [top 3-5 by called_by count]
```

## SAIL Reading Guide

- `rule!Name(...)` — calls expression rule | `cons!Name` — constant reference
- `a!textField`, `a!dropdownField`, `a!gridField` — form fields
- `a!buttonWidget` — button | `a!queryRecordType` — database query
- `if(cond, true, false)` — conditional | `ri!param` — rule input | `local!var` — local variable
- `a!save(target, value)` — save to variable | `a!forEach(items, expression)` — loop

## Guidelines

- Write for a business analyst — NO raw SAIL code in output
- Be specific — use actual field names, record type names, condition values
- Infer purpose from object names when descriptions are empty
- Large bundles (100+ objects): focus on entry point's direct dependencies and top 10 most-connected objects
- Small bundles (<30 objects): describe every object
- Each summary must be self-contained

Start now. Read the `_index.json` first.
