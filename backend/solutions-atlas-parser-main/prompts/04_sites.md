# Generate Summaries — Sites (3 bundles)

I need you to generate business-logic summary documents for all **site** bundles in an Appian application.

Bundles directory: `OUTPUT_DIR/bundles/`

## Instructions

1. Read `OUTPUT_DIR/bundles/_index.json`
2. Filter to entries where `bundle_type` is `"site"`
3. For each site bundle:
   a. Read the JSON file at `OUTPUT_DIR/bundles/{entry.file}`
   b. Analyze it using the rules below
   c. Write a summary markdown file at the same path but with `.md` extension (e.g., `sites/My_Site.json` → `sites/My_Site.md`)
4. After all are done, print how many summaries were written

## How to Analyze Site Bundles

A site bundle represents a **site** — a top-level navigation container that groups pages into an application. Sites define the URL structure, branding, and page hierarchy users see.

### Entry Point Structure
```json
{
  "name": "Site Name",
  "url_stub": "site-url-path",
  "pages": [
    {
      "name": "Page Display Name",
      "url_stub": "page-url-path",
      "ui_object_uuid": "Interface or Record List that renders this page"
    }
  ]
}
```

### Analysis Flow
1. **Site structure**: What's the URL? What pages does it contain? This defines the application's navigation
2. **For each page**: Find the interface referenced by `ui_object_uuid` in `objects.interfaces[]` — read its SAIL code to understand what the page shows
3. **Branding/expressions**: Check for branding expression rules in the bundle — these control the site's appearance
4. **Navigation flow**: How do pages relate to each other? What's the user journey through the site?
5. **Record types**: What business entities are surfaced through this site?

### Output Format

```markdown
# [Site Name]

## Overview
2-3 sentences: what this site/application is, who uses it, what business functions it provides.

## Entry Point
- Type: site
- URL: /[url_stub]
- Pages: [N]

## Navigation Structure
| Page | URL | Description |
|---|---|---|
| [Page Name] | /[site_stub]/[page_stub] | [what this page shows] |
| ... | ... | ... |

## Page Details

### [Page Name]
- **URL**: /[full path]
- **Interface**: [interface name]
- **Purpose**: [what the user sees and does on this page]
- **Key data**: [record types and fields displayed]
- **Actions available**: [buttons, links, navigation options]

(Repeat for each page)

## Data Model
- **[RecordType]**: [how it's surfaced in this site]

## Business Rules
1. [Navigation rules — who can access what]
2. [Branding rules — conditional appearance]

## Key Dependencies
- Total objects: [N]
- Breakdown by type
```

## SAIL Reading Guide

- `rule!Name(...)` — calls expression rule | `cons!Name` — constant reference
- `a!textField`, `a!dropdownField`, `a!gridField` — form fields
- `a!buttonWidget` — button | `a!queryRecordType` — database query
- `a!sitePageLink`, `a!recordLink` — navigation links
- `a!columnsLayout`, `a!sectionLayout` — layout containers

## Guidelines

- Write for a business analyst — NO raw SAIL code in output
- Describe the site as a user would experience it — navigation, pages, actions
- Each summary must be self-contained

Start now. Read the `_index.json` first.
