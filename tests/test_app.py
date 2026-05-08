from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from wechat_to_a2a.a2a_client import A2AReply
from wechat_to_a2a.app import create_app
from wechat_to_a2a.settings import Settings


def _signature(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()


def _query(token: str = "secret") -> str:
    timestamp = "123"
    nonce = "abc"
    return f"signature={_signature(token, timestamp, nonce)}&timestamp={timestamp}&nonce={nonce}"


def _settings(tmp_path) -> Settings:
    return Settings(
        wechat_token="secret",
        upstream_a2a_card_url="https://agent.example/.well-known/agent-card.json",
        conversation_state_path=tmp_path / "conversations.json",
    )


def test_get_wechat_verification_echoes_echostr(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    response = client.get(f"/wechat?{_query()}&echostr=ok")

    assert response.status_code == 200
    assert response.text == "ok"


def test_health(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_requires_wechat_token_for_official_mode() -> None:
    with pytest.raises(RuntimeError, match="WECHAT_TO_A2A_WECHAT_TOKEN"):
        create_app(
            Settings(upstream_a2a_card_url="https://agent.example/.well-known/agent-card.json")
        )


def test_get_wechat_verification_rejects_invalid_signature(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    response = client.get("/wechat?signature=bad&timestamp=123&nonce=abc&echostr=ok")

    assert response.status_code == 403


def test_post_text_message_forwards_to_a2a(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    async def fake_send_message(self, *, text: str, context_id: str | None = None, task_id=None):
        calls.append((text, context_id, task_id))
        return A2AReply(
            text="agent reply", context_id="ctx-user", task_id="task-1", state="completed"
        )

    monkeypatch.setattr("wechat_to_a2a.a2a_client.A2AClient.send_message", fake_send_message)
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    xml = b"""
    <xml>
      <ToUserName><![CDATA[gh_x]]></ToUserName>
      <FromUserName><![CDATA[user-1]]></FromUserName>
      <CreateTime>123</CreateTime>
      <MsgType><![CDATA[text]]></MsgType>
      <Content><![CDATA[hello]]></Content>
    </xml>
    """
    first = client.post(f"/wechat?{_query()}", content=xml)
    second = client.post(f"/wechat?{_query()}", content=xml)

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == [("hello", None, None), ("hello", "ctx-user", None)]
    root = ET.fromstring(first.text)
    assert root.findtext("ToUserName") == "user-1"
    assert root.findtext("FromUserName") == "gh_x"
    assert root.findtext("Content") == "agent reply"


def test_post_non_text_message_returns_unsupported_reply(tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    xml = b"""
    <xml>
      <ToUserName><![CDATA[gh_x]]></ToUserName>
      <FromUserName><![CDATA[user-1]]></FromUserName>
      <CreateTime>123</CreateTime>
      <MsgType><![CDATA[image]]></MsgType>
    </xml>
    """
    response = client.post(f"/wechat?{_query()}", content=xml)

    assert response.status_code == 200
    root = ET.fromstring(response.text)
    assert root.findtext("Content") == "Only text messages are supported right now."
