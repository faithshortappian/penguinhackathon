"""Quick test to verify the master prompt is loaded and used."""
import requests
import json

r = requests.post(
    "http://localhost:8000/api/v1/ai/process",
    json={"prompt": "Write hello world", "code": "", "ruleInputs": []},
    timeout=120,
)

print(f"Status: {r.status_code}")
data = r.json()
print(f"Summary: {data.get('summary')}")
print(f"Code:\n{data.get('code')}")
print(f"Rule Inputs: {data.get('ruleInputs')}")
