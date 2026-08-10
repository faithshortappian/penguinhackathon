from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    appian_base_url: str = "https://your-site.appiancloud.com"
    appian_api_key: str = ""
    cache_ttl_seconds: int = 300  # 5 minute cache

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
