from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx

from wechat_to_a2a.gateway import GatewayReply, WeChatA2AGateway
from wechat_to_a2a.ilink import (
    TYPING_START,
    TYPING_STOP,
    ILinkClient,
    ILinkCredentials,
    ILinkGatewayRunner,
    ILinkStateStore,
    extract_ilink_text,
    parse_ilink_message,
)


def test_extract_ilink_text_reads_text_items() -> None:
    assert extract_ilink_text([{"type": 1, "text_item": {"text": " hello "}}]) == "hello"


def test_extract_ilink_text_falls_back_to_voice_transcript() -> None:
    assert (
        extract_ilink_text([{"type": 3, "voice_item": {"text": "voice transcript"}}])
        == "voice transcript"
    )


def test_parse_ilink_message_skips_self_messages() -> None:
    assert parse_ilink_message({"from_user_id": "acct"}, account_id="acct") is None


def test_ilink_state_store_persists_credentials_and_tokens(tmp_path) -> None:
    store = ILinkStateStore(tmp_path)
    credentials = ILinkCredentials(
        account_id="acct",
        token="token",
        base_url="https://ilink.example",
        user_id="user",
    )

    store.save_credentials(credentials)
    store.save_sync_buf("acct", "sync-1")
    store.set_context_token("acct", "peer", "ctx-token")

    restored = ILinkStateStore(tmp_path)
    assert restored.single_saved_account_id() == "acct"
    assert restored.load_credentials("acct") == credentials
    assert restored.load_sync_buf("acct") == "sync-1"
    assert restored.get_context_token("acct", "peer") == "ctx-token"
    restored.clear_context_token("acct", "peer")
    assert restored.get_context_token("acct", "peer") is None


def test_ilink_state_store_selects_latest_saved_account_when_multiple_exist(tmp_path) -> None:
    store = ILinkStateStore(tmp_path)
    store.save_credentials(ILinkCredentials(account_id="old", token="old-token"))
    store.save_credentials(ILinkCredentials(account_id="new", token="new-token"))
    os.utime(tmp_path / "old.json", ns=(1, 1))
    os.utime(tmp_path / "new.json", ns=(2, 2))

    assert store.single_saved_account_id() is None
    assert store.latest_saved_account_id() == "new"


def test_parse_ilink_message_uses_room_id_as_chat_id() -> None:
    inbound = parse_ilink_message(
        {
            "from_user_id": "sender",
            "room_id": "room",
            "message_id": "msg-1",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        },
        account_id="acct",
    )

    assert inbound is not None
    assert inbound.chat_id == "room"
    assert inbound.sender_id == "sender"


async def test_ilink_client_sends_text_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ilink/bot/sendmessage"
        assert request.headers["authorization"] == "Bearer token"
        body = json.loads(request.content)
        assert body["msg"]["to_user_id"] == "peer"
        assert body["msg"]["context_token"] == "ctx-token"
        assert body["msg"]["item_list"][0]["text_item"]["text"] == "hello"
        return httpx.Response(200, json={"ret": 0})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ILinkClient(
            base_url="https://ilink.example",
            token="token",
            client=http_client,
        )
        response = await client.send_text(
            to_user_id="peer",
            text="hello",
            context_token="ctx-token",
        )

    assert response == {"ret": 0}


async def test_ilink_client_fetches_config_and_sends_typing_payload() -> None:
    seen_config = False
    seen_typing = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_config, seen_typing
        assert request.headers["authorization"] == "Bearer token"
        body = json.loads(request.content)
        if request.url.path == "/ilink/bot/getconfig":
            seen_config = True
            assert body["ilink_user_id"] == "peer"
            assert body["context_token"] == "ctx-token"
            return httpx.Response(200, json={"ret": 0, "typing_ticket": "ticket-1"})
        if request.url.path == "/ilink/bot/sendtyping":
            seen_typing = True
            assert body["ilink_user_id"] == "peer"
            assert body["typing_ticket"] == "ticket-1"
            assert body["status"] == TYPING_START
            return httpx.Response(200, json={"ret": 0})
        raise AssertionError(f"unexpected path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ILinkClient(
            base_url="https://ilink.example",
            token="token",
            client=http_client,
        )
        config = await client.get_config(user_id="peer", context_token="ctx-token")
        response = await client.send_typing(
            to_user_id="peer",
            typing_ticket=str(config["typing_ticket"]),
            status=TYPING_START,
        )

    assert config == {"ret": 0, "typing_ticket": "ticket-1"}
    assert response == {"ret": 0}
    assert seen_config
    assert seen_typing


class FakeGateway:
    def __init__(
        self,
        *,
        fail: bool = False,
        trigger_response_started: bool = True,
        delay_seconds: float = 0.0,
    ) -> None:
        self.messages: list[Any] = []
        self.recorded: list[str] = []
        self.fail = fail
        self.trigger_response_started = trigger_response_started
        self.delay_seconds = delay_seconds

    async def handle_message(
        self,
        message: Any,
        *,
        on_response_started: Callable[[], Awaitable[None] | None] | None = None,
    ) -> GatewayReply:
        self.messages.append(message)
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.trigger_response_started and on_response_started is not None:
            result = on_response_started()
            if result is not None:
                await result
        if self.fail:
            raise RuntimeError("upstream failed")
        return GatewayReply(
            text="reply",
            chunks=["reply"],
            conversation_key="wechat:ilink:acct:peer",
            context_id="ctx-a2a",
            task_id=None,
        )

    def record_outbound_interaction(self, conversation_key: str) -> None:
        self.recorded.append(conversation_key)


class FakeILinkClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, str | None]] = []
        self.typing: list[tuple[str, str, int]] = []
        self.config_calls: list[tuple[str, str | None]] = []

    async def send_text(
        self,
        *,
        to_user_id: str,
        text: str,
        context_token: str,
        client_id: str | None = None,
    ) -> dict[str, int]:
        self.sent.append((to_user_id, text, context_token, client_id))
        return {"ret": 0}

    async def get_config(self, *, user_id: str, context_token: str | None) -> dict[str, object]:
        self.config_calls.append((user_id, context_token))
        return {"ret": 0, "typing_ticket": "ticket-1"}

    async def send_typing(
        self,
        *,
        to_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> dict[str, int]:
        self.typing.append((to_user_id, typing_ticket, status))
        return {"ret": 0}


async def test_ilink_runner_forwards_text_to_a2a_and_replies(tmp_path) -> None:
    store = ILinkStateStore(tmp_path)
    gateway = FakeGateway()
    ilink_client = FakeILinkClient()
    runner = ILinkGatewayRunner(
        account_id="acct",
        ilink_client=cast(ILinkClient, ilink_client),
        gateway=cast(WeChatA2AGateway, gateway),
        state_store=store,
        send_chunk_delay_seconds=0,
    )

    reply = await runner.handle_raw_message(
        {
            "from_user_id": "peer",
            "message_id": "msg-1",
            "context_token": "ctx-token",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        }
    )

    assert reply is not None
    assert gateway.messages[0].gateway == "ilink"
    assert gateway.messages[0].from_user == "peer"
    assert gateway.messages[0].content == "hi"
    assert ilink_client.config_calls == [("peer", "ctx-token")]
    assert ilink_client.typing == []
    assert ilink_client.sent == [("peer", "reply", "ctx-token", None)]
    assert gateway.recorded == ["wechat:ilink:acct:peer"]


async def test_ilink_runner_reports_upstream_errors_without_raising(tmp_path) -> None:
    store = ILinkStateStore(tmp_path)
    gateway = FakeGateway(fail=True)
    ilink_client = FakeILinkClient()
    runner = ILinkGatewayRunner(
        account_id="acct",
        ilink_client=cast(ILinkClient, ilink_client),
        gateway=cast(WeChatA2AGateway, gateway),
        state_store=store,
        send_chunk_delay_seconds=0,
    )

    reply = await runner.handle_raw_message(
        {
            "from_user_id": "peer",
            "message_id": "msg-1",
            "context_token": "ctx-token",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        }
    )

    assert reply is None
    assert ilink_client.config_calls == [("peer", "ctx-token")]
    assert ilink_client.typing == []
    assert ilink_client.sent == [
        ("peer", "The upstream A2A agent is unavailable.", "ctx-token", None)
    ]
    assert gateway.recorded == []


async def test_ilink_runner_uses_delayed_typing_for_slow_turn(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("wechat_to_a2a.ilink.TYPING_REFRESH_SECONDS", 0.01)
    monkeypatch.setattr("wechat_to_a2a.ilink.TYPING_SEND_TIMEOUT_SECONDS", 0.25)
    store = ILinkStateStore(tmp_path)
    gateway = FakeGateway(trigger_response_started=False, delay_seconds=0.01)
    ilink_client = FakeILinkClient()
    runner = ILinkGatewayRunner(
        account_id="acct",
        ilink_client=cast(ILinkClient, ilink_client),
        gateway=cast(WeChatA2AGateway, gateway),
        state_store=store,
        send_chunk_delay_seconds=0,
    )

    reply = await runner.handle_raw_message(
        {
            "from_user_id": "peer",
            "message_id": "msg-1",
            "context_token": "ctx-token",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        }
    )

    assert reply is not None
    assert ilink_client.config_calls == [("peer", "ctx-token")]
    assert ilink_client.typing == [
        ("peer", "ticket-1", TYPING_START),
        ("peer", "ticket-1", TYPING_STOP),
    ]


async def test_ilink_runner_skips_late_typing_start_for_fast_turn(tmp_path) -> None:
    store = ILinkStateStore(tmp_path)
    gateway = FakeGateway(trigger_response_started=True, delay_seconds=0.0)
    ilink_client = FakeILinkClient()
    runner = ILinkGatewayRunner(
        account_id="acct",
        ilink_client=cast(ILinkClient, ilink_client),
        gateway=cast(WeChatA2AGateway, gateway),
        state_store=store,
        send_chunk_delay_seconds=0,
    )

    reply = await runner.handle_raw_message(
        {
            "from_user_id": "peer",
            "message_id": "msg-1",
            "context_token": "ctx-token",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        }
    )

    assert reply is not None
    assert ilink_client.config_calls == [("peer", "ctx-token")]
    assert ilink_client.typing == []
