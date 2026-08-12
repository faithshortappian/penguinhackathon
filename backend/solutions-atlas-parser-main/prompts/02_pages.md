# Generate Summaries — Pages (47 bundles)

I need you to generate business-logic summary documents for all **page** bundles in an Appian application.

Bundles directory: `OUTPUT_DIR/bundles/`

## Instructions

1. Read `OUTPUT_DIR/bundles/_index.json`
2. Filter to entries where `bundle_type` is `"page"`
3. For each page bundle:
   a. Read the JSON file at `OUTPUT_DIR/bundles/{entry.file}`
   b. Analyze it using the rules below
   c. Write a summary markdown file at the same path but with `.md` extension (e.g., `pages/My_Page.json` → `pages/My_Page.md`)
4. After all are done, print how many summaries were written

## How to Analyze Page Bundles

A page bundle represents a **record type's views** — the screens users see when browsing or viewing records (summary dashboards, detail views, list views).

### Entry Point Structure
```json
{
  "name": "RecordType Name",
  "record_type": "The record type these views belong to",
  "views": [
    {
      "view_type": "SUMMARY|RECORD_LIST|HEADER|FEED|...",
      "view_name": "Display name",
      "ui_expr": "Interface that renders this view"
    }
  ]
}
```

### Analysis Flow
1. **Start with the record type**: What business entity does this represent? Read its fields and relationships from `objects.record_types[]`
2. **Walk each view**: For each view in `entry_point.views[]`:
   - Find the interface referenced by `ui_expr` in `objects.interfaces[]`
   - Read its `data.sail_code` to understand the screen layout
   - Identify: what data is displayed, what filters/search are available, what actions can be triggered
3. **View types**:
   - `SUMMARY` — dashboard/overview shown at the top of a record
   - `RECORD_LIST` — the list/grid view for browsing records
   - `HEADER` — the record header bar
   - `FEED` — activity feed/timeline
   - Other custom views
4. **Trace expression rules**: Rules called by the interfaces — these contain query logic, formatting, permissions
5. **Identify data flow**: What record fields are displayed? What related records are shown?

### Output Format

```markdown
# [Record Type Name] — Pages

## Overview
2-3 sentences: what record type this is, what views are available, what business purpose they serve.

## Entry Point
- Type: page
- Record Type: [X]
- Views: [N] — [list view types and names]

## Views

### [View Name] ([VIEW_TYPE])
- **Purpose**: [what this view shows]
- **Layout**: [describe the screen — sections, tabs, columns]
- **Data displayed**: [key fields and related data shown]
- **Filters/Search**: [any filtering or search capabilities]
- **Actions available**: [buttons, links, record actions accessible from this view]

(Repeat for each view)

## Data Model
- **[RecordType]**: [key fields displayed across views]
- **[Related RecordType]**: [relationship and how it's shown]

## Business Rules
1. [Visibility/permission rules — who sees what]
2. [Conditional display rules — when certain sections show/hide]
3. [Data formatting rules — how values are presented]

## User Interactions
- **[Screen/Section]**: [what the user can do here]

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
- `a!columnsLayout`, `a!sectionLayout`, `a!cardLayout` — layout containers
- `a!linkField`, `a!recordLink` — navigation links
- `a!richTextDisplayField` — formatted text display

## Guidelines

- Write for a business analyst — NO raw SAIL code in output
- Be specific — use actual field names, record type names
- Describe each view as a screen a user would see
- Infer purpose from object names when descriptions are empty
- Large bundles (100+ objects): focus on the views and their direct dependencies
- Each summary must be self-contained

Start now. Read the `_index.json` first.
