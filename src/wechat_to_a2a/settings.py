from __future__ import annotations

from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_conversation_state_path() -> Path:
    return Path.home() / ".wechat_to_a2a" / "conversations.json"


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

    @property
    def upstream_a2a_card_url_value(self) -> str:
        return str(self.upstream_a2a_card_url)
