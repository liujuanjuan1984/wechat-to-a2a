from __future__ import annotations

from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WECHAT_TO_A2A_", extra="ignore")

    wechat_token: str | None = Field(default=None, min_length=1)
    a2a_url: AnyHttpUrl
    a2a_bearer_token: str | None = None
    a2a_timeout_seconds: float = Field(default=30.0, gt=0)
    conversation_state_path: Path | None = None
    wechat_reply_max_chars: int = Field(default=2000, gt=0)
    wechat_split_multiline_messages: bool = False

    @property
    def a2a_endpoint(self) -> str:
        return str(self.a2a_url)
