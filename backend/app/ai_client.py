"""AI client using Google Gemini Interactions API for SAIL code processing."""

import json
from google import genai
from app.config import get_settings


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

Your response MUST be valid JSON with exactly these fields:
- "summary": A brief explanation of what was done (1-3 sentences)
- "code": The processed/improved SAIL expression (valid SAIL code)
- "ruleInputs": An array of rule input objects, each with "name" and "type" fields

Do NOT include markdown code fences or any other text outside the JSON object."""

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

            return {
                "summary": result.get("summary", ""),
                "code": result.get("code", code),
                "ruleInputs": result.get("ruleInputs", rule_inputs),
            }

        except json.JSONDecodeError:
            # If the model didn't return valid JSON, wrap the raw text
            return {
                "summary": "AI returned a response but it was not in the expected format.",
                "code": response_text if response_text else code,
                "ruleInputs": rule_inputs,
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
