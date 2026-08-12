"""AI client using Google Gemini Interactions API for SAIL code processing."""

import json
import re
from google import genai
from app.config import get_settings
from app.syntax_check import check_balanced_brackets


class AIClient:
    """Handles LLM interactions via Google Gemini (AI Studio)."""

    def __init__(self):
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model

    def _build_system_prompt(self, docs_context: str, app_context: str) -> str:
        """Build the system prompt with Appian documentation and app context."""
        return f"""You are an expert Appian SAIL developer. You help users write, fix, and improve SAIL expressions and interfaces.

You have access to the following Appian documentation context:
<appian_docs>
{docs_context}
</appian_docs>

You also have context about the user's Appian application:
<app_context>
{app_context}
</app_context>

When responding:
1. Always return valid SAIL code.
2. Reference existing rule!, const!, and recordType! objects from the app context when appropriate.
3. Follow Appian best practices for performance and readability.
4. Explain what you changed in the summary.
5. If the user provides rule inputs, incorporate them correctly using ri! references.

SAIL conventions (follow strictly):
- Use lowercase function/component prefixes exactly as Appian defines them (a!, ri!, rule!, const!, recordType!, fv!, save!, pv!) — never invent or guess a prefix.
- Prefer local variables (a!localVariables()) over repeating the same sub-expression multiple times.
- Do not use deprecated functions or components; if the docs context flags something as deprecated, use the recommended replacement instead.
- Match existing naming conventions already present in the user's code or app context rather than introducing new ones.
- Keep expressions readable: break complex nested a! calls across lines rather than producing a single dense line.

Grounding discipline:
- Only reference SAIL functions, components, or parameters that either appear in <appian_docs> below or that you are highly confident are core, stable Appian SAIL syntax.
- If <appian_docs> is empty or does not cover something you need, say so explicitly in the summary (e.g. "no documentation was found for X, verify usage") rather than inventing behavior.
- Do not fabricate rule!, const!, or recordType! names that are not present in <app_context> — if a needed object doesn't exist there, note in the summary that it needs to be created.

Respond with:
- "summary": A brief explanation of what was done (1-3 sentences)
- "code": The processed/improved SAIL expression (valid SAIL code)
- "ruleInputs": An array of rule input objects, each with "name" and "type" fields"""

    _RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "code": {"type": "string"},
            "ruleInputs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                    },
                    "required": ["name", "type"],
                },
            },
        },
        "required": ["summary", "code", "ruleInputs"],
    }

    def _build_user_message(self, code: str, prompt: str, rule_inputs: list[dict]) -> str:
        """Build the user message with code, prompt, and rule inputs."""
        parts = []

        if prompt:
            parts.append(f"User request: {prompt}")

        if code:
            parts.append(f"Current SAIL code:\n```\n{code}\n```")

        if rule_inputs:
            inputs_str = json.dumps(rule_inputs, indent=2)
            parts.append(f"Rule inputs:\n{inputs_str}")

        return "\n\n".join(parts)

    async def process_expression(
        self,
        code: str,
        prompt: str,
        rule_inputs: list[dict],
        docs_context: str = "",
        app_context: str = "",
    ) -> dict:
        """
        Process a SAIL expression through the AI model.

        Args:
            code: The SAIL expression to process
            prompt: User's instruction/question
            rule_inputs: List of rule input definitions [{name, type}]
            docs_context: Relevant Appian documentation
            app_context: Application context (record types, rules, etc.)

        Returns:
            dict with summary, code, and ruleInputs
        """
        system_prompt = self._build_system_prompt(docs_context, app_context)
        user_message = self._build_user_message(code, prompt, rule_inputs)

        full_input = f"{system_prompt}\n\n---\n\n{user_message}"

        try:
            interaction = self.client.interactions.create(
                model=self.model,
                input=full_input,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": self._RESPONSE_SCHEMA,
                },
            )

            response_text = interaction.output_text

            # Parse the JSON response
            # Strip potential markdown fences if model adds them despite instructions
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                # Remove code fence
                lines = cleaned.split("\n")
                lines = lines[1:]  # Remove opening ```json or ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)

            result = json.loads(cleaned)
            final_code = result.get("code", code)

            return {
                "summary": result.get("summary", ""),
                "code": final_code,
                "ruleInputs": result.get("ruleInputs", rule_inputs),
                "syntaxWarnings": check_balanced_brackets(final_code),
            }

        except json.JSONDecodeError:
            # Malformed JSON from the model (e.g. a bad escape sequence). Try to
            # salvage the "code" field with a regex rather than pasting the raw,
            # still-JSON-shaped response text into the SAIL editor.
            salvaged_code = None
            match = re.search(r'"code"\s*:\s*"(.*?)"\s*,\s*"ruleInputs"', response_text, re.DOTALL)
            if match:
                try:
                    salvaged_code = json.loads(f'"{match.group(1)}"')
                except json.JSONDecodeError:
                    salvaged_code = None

            final_code = salvaged_code if salvaged_code else code

            return {
                "summary": "AI returned a response but it was not in the expected format.",
                "code": final_code,
                "ruleInputs": rule_inputs,
                "syntaxWarnings": check_balanced_brackets(final_code),
            }
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {str(e)}") from e


# Singleton (reset on module reload)
_ai_client: AIClient | None = None


def get_ai_client() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
