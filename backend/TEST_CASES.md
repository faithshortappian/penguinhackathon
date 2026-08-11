# Backend Test Cases

Make sure the server is running first:
```powershell
cd c:\Users\faith.short\penguinhackathon\backend
py -m uvicorn app.main:app --port 8000
```

Then run each test in a separate PowerShell window.

---

## Test 1: Simple prompt, no code

**Input:** Ask the AI to generate a SAIL expression from scratch.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ai/process" -Method POST -ContentType "application/json" -Body '{"prompt": "Write a SAIL expression that returns hello world", "code": "", "ruleInputs": []}' | ConvertTo-Json -Depth 5
```

**Expected output shape:**
```json
{
  "summary": "Created a simple SAIL expression that returns the text Hello World.",
  "code": "\"Hello World\"",
  "ruleInputs": []
}
```

---

## Test 2: Improve existing code

**Input:** Give it existing SAIL code and ask for improvement.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ai/process" -Method POST -ContentType "application/json" -Body '{"prompt": "Add null safety to this expression", "code": "a!localVariables(\n  local!items: ri!inputList,\n  sum(local!items)\n)", "ruleInputs": [{"name": "inputList", "type": "Number (Integer)"}]}' | ConvertTo-Json -Depth 5
```

**Expected output shape:**
```json
{
  "summary": "Added null check to handle empty or null input list before summing.",
  "code": "a!localVariables(\n  local!items: ri!inputList,\n  if(\n    or(isnull(local!items), length(local!items) = 0),\n    0,\n    sum(local!items)\n  )\n)",
  "ruleInputs": [
    { "name": "inputList", "type": "Number (Integer)" }
  ]
}
```

---

## Test 3: Generate code with rule inputs

**Input:** Ask for a new expression rule with specific inputs.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ai/process" -Method POST -ContentType "application/json" -Body '{"prompt": "Create an expression rule that concatenates first and last name with a space between them", "code": "", "ruleInputs": [{"name": "firstName", "type": "Text"}, {"name": "lastName", "type": "Text"}]}' | ConvertTo-Json -Depth 5
```

**Expected output shape:**
```json
{
  "summary": "Created an expression that concatenates first and last name with a space separator.",
  "code": "ri!firstName & \" \" & ri!lastName",
  "ruleInputs": [
    { "name": "firstName", "type": "Text" },
    { "name": "lastName", "type": "Text" }
  ]
}
```

---

## Test 4: Fix broken code

**Input:** Send code with a syntax issue and ask the AI to fix it.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ai/process" -Method POST -ContentType "application/json" -Body '{"prompt": "Fix this expression - it has a syntax error", "code": "a!localVariables(\n  local!name: \"John\",\n  local!greeting: \"Hello \" & local!name\n  local!greeting\n)", "ruleInputs": []}' | ConvertTo-Json -Depth 5
```

**Expected output shape:**
```json
{
  "summary": "Fixed missing comma between the local variable declaration and the return value.",
  "code": "a!localVariables(\n  local!name: \"John\",\n  local!greeting: \"Hello \" & local!name,\n  local!greeting\n)",
  "ruleInputs": []
}
```

---

## Test 5: Complex query with record type context

**Input:** Ask for a record query expression with inputs.

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ai/process" -Method POST -ContentType "application/json" -Body '{"prompt": "Write a query that filters customers by status and returns their names", "code": "", "ruleInputs": [{"name": "status", "type": "Text"}]}' | ConvertTo-Json -Depth 5
```

**Expected output shape:**
```json
{
  "summary": "Created a record query that filters customers by status and returns their names.",
  "code": "a!queryRecordType(\n  recordType: recordType!Customer,\n  filters: a!queryFilter(\n    field: recordType!Customer.fields.status,\n    operator: \"=\",\n    value: ri!status\n  ),\n  fields: {\n    recordType!Customer.fields.name\n  },\n  pagingInfo: a!pagingInfo(startIndex: 1, batchSize: 100)\n).data",
  "ruleInputs": [
    { "name": "status", "type": "Text" }
  ]
}
```

---

## Test 6: Health check

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
```

**Expected:** `{"status": "ok"}`

---

## Notes

- Exact code output will vary since the AI generates it dynamically.
- What matters is: `summary` explains the change, `code` is valid SAIL, `ruleInputs` reflects input params.
- First request may take 10-30 seconds (Gemini + docs MCP lookup). Subsequent ones are faster.
- If you get a timeout, just wait — the server log should show `200 OK` when it completes.
