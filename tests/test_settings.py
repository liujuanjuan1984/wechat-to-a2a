from __future__ import annotations

import stat
from pathlib import Path

from wechat_to_a2a.settings import (
    Settings,
    default_config_path,
    default_conversation_state_path,
    load_persistent_config,
    save_upstream_config,
)


def test_default_conversation_state_path_uses_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: Path("/home/tester"))

    assert default_conversation_state_path() == Path(
        "/home/tester/.wechat_to_a2a/conversations.json"
    )


def test_default_config_path_uses_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: Path("/home/tester"))

    assert default_config_path() == Path("/home/tester/.wechat_to_a2a/config.json")


def test_settings_uses_upstream_agent_card_url() -> None:
    settings = Settings.model_validate(
        {"upstream_a2a_card_url": "https://agent.example/.well-known/agent-card.json"}
    )

    assert (
        settings.upstream_a2a_card_url_value == "https://agent.example/.well-known/agent-card.json"
    )


def test_persistent_config_round_trips_upstream_values(tmp_path) -> None:
    config_path = tmp_path / ".wechat_to_a2a" / "config.json"

    saved_path = save_upstream_config(
        card_url="https://agent.example/.well-known/agent-card.json",
        bearer_token="secret",
        path=config_path,
    )

    assert saved_path == config_path
    assert load_persistent_config(config_path) == {
        "upstream_a2a_card_url": "https://agent.example/.well-known/agent-card.json",
        "upstream_a2a_bearer_token": "secret",
    }
    assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_persistent_config_can_clear_bearer_token(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    save_upstream_config(
        card_url="https://agent.example/.well-known/agent-card.json",
        bearer_token="secret",
        path=config_path,
    )

    save_upstream_config(
        card_url="https://agent.example/.well-known/agent-card.json",
        clear_bearer_token=True,
        path=config_path,
    )

    assert load_persistent_config(config_path) == {
        "upstream_a2a_card_url": "https://agent.example/.well-known/agent-card.json"
    }
