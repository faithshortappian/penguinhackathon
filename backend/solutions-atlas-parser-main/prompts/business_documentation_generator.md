# Business Documentation Generator — Kiro Prompt

## How to Use

Copy the entire prompt below (everything between the `---START---` and `---END---` markers) and paste it into a Kiro CLI chat session. Replace the placeholder paths if your output directory is different.

**Prerequisites:** Run the parser first — the `dump` command now generates a `documentation_context.json` file alongside the other outputs. This single file contains everything the AI needs.

```bash
python -m appian_parser dump MyApp.zip ./output
# Output now includes: documentation_context.json (829KB vs 19MB of individual files)
```

---START---

I need you to generate comprehensive business documentation for an Appian application. The parser has already extracted and pre-aggregated all the data into a single context file:

```
/Users/ramaswamy.u/Documents/appianParserTesting/outputs
```

Read that file. It contains all the information you need in one place:

- `app_overview` — package info, object counts by type, dependency statistics (top 20 most depended-on, top 20 most dependencies, counts by dependency type)
- `sites` — all sites with their page hierarchy, target UUIDs, and roles
- `data_model.record_types` — all 48 record types with fields, relationships, actions, and views
- `data_model.cdts` — all 107 CDTs with field definitions
- `processes` — all 108 process models with nodes (including gateway conditions, interface references, subprocess targets), variables, and complexity scores
- `integrations` — all 14 integrations with connected system names, HTTP methods, URLs, and auth types
- `connected_systems` — all 6 connected systems with base URLs and auth types
- `web_apis` — all 4 web APIs with URL aliases, HTTP methods, and SAIL code
- `groups` — all 93 groups with parent group names, group types, and member counts
- `constants_summary` — total count, naming pattern analysis, and 20 samples
- `top_expression_rules` — top 30 by inbound dependency count, with SAIL code, inputs, output type, and descriptions
- `top_interfaces` — top 30 by inbound dependency count, with SAIL code, parameters, and descriptions
- `security_samples` — security configurations from 15 representative objects

SAIL code has already been resolved — UUIDs replaced with `rule!ObjectName`, `cons!ConstantName`, `recordType!RecordType.field`, and translation URNs replaced with actual text.

## Your Task

Generate a business documentation document using a **2-pass strategy**. Write the final document to:

```
/Users/ramaswamy.u/Documents/appianParserTesting/outputs/v1/BUSINESS_DOCUMENTATION.md
```

### Pass 1: Analysis (use 4 parallel subagents)

All subagents should read `documentation_context.json` first, then focus on their assigned sections.

**Subagent 1 — Application Overview & Data Model:**
- From `app_overview`: summarize what the application is, its scale, and dependency landscape
- From `sites`: describe the navigation structure and page hierarchy
- From `data_model`: describe all record types and CDTs — entity relationships, central entities, what business entities they represent
- Produce a written summary covering: executive summary, application overview, and data model sections

**Subagent 2 — Business Processes & Flow Tracing:**
- From `processes`: analyze all process models — their purpose, complexity, decision points (gateway conditions), forms (interface references), and how they chain together (subprocess references)
- Trace 3-5 complete business flows end-to-end: Site pages → Record Type actions → Process Models → Interface references in nodes
- Produce a written summary covering: business processes and user experience sections

**Subagent 3 — Integrations & Security:**
- From `integrations`, `connected_systems`, `web_apis`: describe the external system landscape
- From `groups` and `security_samples`: describe the group hierarchy, role-based access patterns, and permission model
- Produce a written summary covering: external integrations and security model sections

**Subagent 4 — Business Logic & Metrics:**
- From `top_expression_rules`: analyze the core shared business logic — what patterns are used, what business rules are encoded, what validations exist
- From `top_interfaces`: analyze the key user-facing screens — what data they display/collect, what actions they enable
- From `app_overview`: compile application metrics and complexity indicators
- Produce a written summary covering: business rules & logic, application metrics, and appendix sections

### Pass 2: Document Assembly (single agent)

Using ALL summaries from Pass 1, write the final `BUSINESS_DOCUMENTATION.md` with these sections:

```markdown
# [Application Name] — Business Documentation

## Executive Summary
2-3 paragraphs: what this application does, who uses it, what business problem it solves.

## Application Overview
- Sites and navigation structure
- Object composition (counts by type, what this tells us about complexity)
- External system landscape

## Data Model
- Entity relationship descriptions in plain English
- Central entities and their business meaning
- Data flow: where data comes from, how it's transformed, where it goes

## Business Processes
For each major process:
- Purpose and trigger
- Step-by-step workflow narrative
- Decision points and business rules
- Forms and user interactions
- Outcomes and side effects

## User Experience
- Site navigation and page structure
- Key screens and what they do
- User workflows (end-to-end journeys)

## External Integrations
- Connected systems and their purpose
- Outbound API calls (what data is sent where)
- Inbound API endpoints (what data is received)

## Security Model
- Group hierarchy and roles
- Access control patterns
- Permission model

## Business Rules & Logic
- Core shared rules and what they enforce
- Validation patterns
- Calculation logic

## Application Metrics
- Total objects by type
- Dependency statistics
- Complexity indicators (most complex process models, most connected objects)

## Appendix: Object Inventory
- Table of all record types with field counts
- Table of all process models with complexity scores
- Table of all integrations with HTTP methods and URLs
```

Important guidelines:
- Write for a **business audience** — avoid technical jargon where possible, explain Appian concepts in plain English
- When referencing specific objects, use their names (not UUIDs)
- Include specific numbers and counts to make the document concrete
- If a description field is empty, infer purpose from the object name and its SAIL code/structure
- The document should be **self-contained** — someone who has never seen the Appian application should understand what it does after reading this

---END---
