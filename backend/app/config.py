from pydantic_settings import BaseSettings


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

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
