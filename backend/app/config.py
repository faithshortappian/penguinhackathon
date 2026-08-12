from pathlib import Path

from pydantic_settings import BaseSettings

# Default prompt file lives at repo root
_DEFAULT_PROMPT_PATH = str(
    Path(__file__).resolve().parent.parent.parent / "appian_sail_agent_master_prompt.md"
)


class Settings(BaseSettings):
    # Appian Design API (direct REST)
    appian_base_url: str = "https://your-site.appiancloud.com"
    appian_api_key: str = ""
    cache_ttl_seconds: int = 300  # 5 minute cache

    # Appian Native MCP (HTTP endpoint)
    appian_native_url: str = "https://your-site.appiancloud.com/mcp"
    appian_native_token: str = ""

    # Appian Docs MCP (HTTP endpoint)
    appian_docs_url: str = "https://appian-docs-api.mcp.kapa.ai"
    appian_docs_token: str = ""

    # Google Gemini AI (AI Studio)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # System prompt — path to the master SAIL agent prompt file
    system_prompt_path: str = _DEFAULT_PROMPT_PATH

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
