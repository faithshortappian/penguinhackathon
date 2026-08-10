"""HTTP client for Appian Design API calls."""

import httpx
from cachetools import TTLCache
from app.config import get_settings


class AppianClient:
    """Thin wrapper around Appian's Design API."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.appian_base_url.rstrip("/")
        self.headers = {
            "Appian-API-Key": settings.appian_api_key,
            "Content-Type": "application/json",
        }
        self._cache = TTLCache(maxsize=256, ttl=settings.cache_ttl_seconds)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        cache_key = f"{path}:{params}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            self._cache[cache_key] = data
            return data

    # ─── Application ────────────────────────────────────────────

    async def get_application(self, app_uuid: str) -> dict:
        return await self._get(f"/design/v1/applications/{app_uuid}")

    async def list_objects_in_app(self, app_uuid: str, object_type: str, limit: int = 50, offset: int = 0) -> dict:
        return await self._get(
            f"/design/v1/{object_type}",
            params={"appUuid": app_uuid, "limit": limit, "offset": offset},
        )

    # ─── Record Types ───────────────────────────────────────────

    async def get_record_type(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/record-types/{uuid}")

    async def list_record_type_fields(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/record-types/{uuid}/fields")

    async def list_record_type_relationships(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/record-types/{uuid}/relationships")

    # ─── Expression Rules ───────────────────────────────────────

    async def get_expression_rule(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/expression-rules/{uuid}")

    # ─── Interfaces ─────────────────────────────────────────────

    async def get_interface(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/interfaces/{uuid}")

    # ─── Constants ──────────────────────────────────────────────

    async def get_constant(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/constants/{uuid}")

    # ─── Process Models ─────────────────────────────────────────

    async def get_process_model(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/process-models/{uuid}")

    # ─── Integrations ───────────────────────────────────────────

    async def get_integration(self, uuid: str) -> dict:
        return await self._get(f"/design/v1/integrations/{uuid}")

    # ─── Groups ─────────────────────────────────────────────────

    async def list_groups(self, app_uuid: str, limit: int = 50) -> dict:
        return await self._get(
            "/design/v1/groups",
            params={"appUuid": app_uuid, "limit": limit},
        )


def get_appian_client() -> AppianClient:
    return AppianClient()
