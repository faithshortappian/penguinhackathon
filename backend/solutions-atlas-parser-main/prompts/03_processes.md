# Generate Summaries — Processes (108 bundles)

I need you to generate business-logic summary documents for all **process** bundles in an Appian application. There are 108 process bundles — process them in order. If the session runs out of context, note where you stopped so I can continue in a new session.

Bundles directory: `OUTPUT_DIR/bundles/`

## Instructions

1. Read `OUTPUT_DIR/bundles/_index.json`
2. Filter to entries where `bundle_type` is `"process"`
3. For each process bundle:
   a. Read the JSON file at `OUTPUT_DIR/bundles/{entry.file}`
   b. Analyze it using the rules below
   c. Write a summary markdown file at the same path but with `.md` extension (e.g., `processes/My_Process.json` → `processes/My_Process.md`)
4. After all are done (or if stopping mid-way), print how many summaries were written and which bundles remain

## How to Analyze Process Bundles

A process bundle represents a **standalone process model** — a workflow not triggered by any record action (it's either scheduled, triggered by another system, or started manually).

### Entry Point Structure
```json
{
  "name": "Process Name",
  "complexity_score": 10.0,
  "total_nodes": 6
}
```

### Analysis Flow
1. **Read process nodes**: Find the process in `objects.processes[]`, read `data.nodes[]` in sequence
2. **Walk the flow**:
   - **Start Event** → first activity
   - **Script Task / Custom Output**: executes expression rules (business logic)
   - **User Input Task**: shows a form to a user — read `form_expression` to find the interface
   - **Gateway (XOR/AND)**: decision point — read `gateway_conditions[].condition` for the business rule
   - **Subprocess**: calls another process — note what it does
   - **Send Email / Notification**: communication step
   - **End Event**: process completes — what's the outcome?
3. **Read process variables**: `data.variables[]` — these are the data flowing through the process
4. **Trace expression rules**: Rules called by nodes contain the actual business logic
5. **Identify interfaces**: Forms shown in User Input tasks — describe what the user sees

### Output Format

```markdown
# [Process Name]

## Overview
2-3 sentences: what this process does, when it runs, what business outcome it produces.

## Entry Point
- Type: process
- Complexity: [score] ([total_nodes] nodes)
- Trigger: [infer from name/context — scheduled, manual, system-triggered]

## Business Logic Flow
Step-by-step walkthrough of the process:
1. Process starts — [initial context/data]
2. [Step]: [what happens — data read, written, transformed]
3. [Decision]: [translate gateway condition to business rule, describe each branch]
4. [User Task]: [describe the form — what data is shown, what user enters]
5. [Step]: [next activity]
6. Process ends — [outcome, what changed]

## Data Model
- **[RecordType]**: [role in this process, key fields read/written]

## Business Rules
1. [Gateway decisions in plain English]
2. [Validation rules from forms]
3. [Conditional logic from expression rules]

## User Interactions
(only if User Input tasks exist)
- **[Form Name]**: [fields, data collected, buttons]

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
- Large bundles (100+ objects): focus on the process nodes, their direct expression rules, and top 10 most-connected objects
- Small bundles (<30 objects): describe every object
- Each summary must be self-contained
- If you run out of context, clearly state which bundle you stopped at

Start now. Read the `_index.json` first.
