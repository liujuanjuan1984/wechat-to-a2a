from __future__ import annotations

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WECHAT_TO_A2A_", extra="ignore")

    wechat_token: str = Field(min_length=1)
    a2a_url: AnyHttpUrl
    a2a_bearer_token: str | None = None
    a2a_timeout_seconds: float = Field(default=30.0, gt=0)

    @property
    def a2a_endpoint(self) -> str:
        return str(self.a2a_url)
