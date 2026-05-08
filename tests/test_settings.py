from __future__ import annotations

from pathlib import Path

from wechat_a2a_gateway.settings import Settings, default_conversation_state_path


def test_default_conversation_state_path_uses_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: Path("/home/tester"))

    assert default_conversation_state_path() == Path(
        "/home/tester/.wechat_to_a2a/conversations.json"
    )


def test_settings_uses_upstream_agent_card_url() -> None:
    settings = Settings(upstream_a2a_card_url="https://agent.example/.well-known/agent-card.json")

    assert (
        settings.upstream_a2a_card_endpoint == "https://agent.example/.well-known/agent-card.json"
    )
