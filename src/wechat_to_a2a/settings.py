from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

UPSTREAM_A2A_CARD_URL_ENV = "WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL"
UPSTREAM_A2A_BEARER_TOKEN_ENV = "WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN"


def default_conversation_state_path() -> Path:
    return Path.home() / ".wechat_to_a2a" / "conversations.json"


def default_config_path() -> Path:
    return Path.home() / ".wechat_to_a2a" / "config.json"


def load_persistent_config(path: Path | None = None) -> dict[str, str]:
    config_path = path or default_config_path()
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid config file: {config_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid config file: {config_path}")
    return {
        key: value
        for key, value in payload.items()
        if key in {"upstream_a2a_card_url", "upstream_a2a_bearer_token"}
        and isinstance(value, str)
        and value
    }


def save_upstream_config(
    *,
    card_url: str,
    bearer_token: str | None = None,
    clear_bearer_token: bool = False,
    path: Path | None = None,
) -> Path:
    config_path = path or default_config_path()
    values = load_persistent_config(config_path)
    values["upstream_a2a_card_url"] = card_url
    if clear_bearer_token:
        values.pop("upstream_a2a_bearer_token", None)
    elif bearer_token:
        values["upstream_a2a_bearer_token"] = bearer_token

    Settings.model_validate(values)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(config_path.parent, 0o700)
    _write_private_json(config_path, values)
    return config_path


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, sort_keys=True)
            file.write("\n")
    finally:
        os.chmod(path, 0o600)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WECHAT_TO_A2A_", extra="ignore")

    wechat_token: str | None = Field(default=None, min_length=1)
    upstream_a2a_card_url: AnyHttpUrl
    upstream_a2a_bearer_token: str | None = None
    upstream_a2a_timeout_seconds: float = Field(default=300.0, gt=0)
    upstream_a2a_stream_idle_timeout_seconds: float = Field(default=60.0, ge=0)
    conversation_state_path: Path = Field(default_factory=default_conversation_state_path)
    wechat_reply_max_chars: int = Field(default=2000, gt=0)
    wechat_split_multiline_messages: bool = False
