"""Persistent token storage for OAuth-authenticated MCP servers."""

import json
from pathlib import Path
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


TOKENS_DIR = Path(__file__).parent.parent / ".tokens"


class FileTokenStorage:
    """Stores OAuth tokens and client info to disk so they persist across restarts."""

    def __init__(self, server_name: str):
        self._dir = TOKENS_DIR / server_name
        self._dir.mkdir(parents=True, exist_ok=True)
        self._token_file = self._dir / "tokens.json"
        self._client_file = self._dir / "client_info.json"

    async def get_tokens(self) -> OAuthToken | None:
        if not self._token_file.exists():
            return None
        data = json.loads(self._token_file.read_text())
        return OAuthToken(**data)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._token_file.write_text(tokens.model_dump_json(indent=2))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        if not self._client_file.exists():
            return None
        data = json.loads(self._client_file.read_text())
        return OAuthClientInformationFull(**data)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_file.write_text(client_info.model_dump_json(indent=2))
