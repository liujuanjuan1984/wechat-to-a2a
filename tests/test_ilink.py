from __future__ import annotations

import json

import httpx

from wechat_a2a_gateway.gateway import GatewayReply
from wechat_a2a_gateway.ilink import (
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


class FakeGateway:
    def __init__(self) -> None:
        self.messages = []

    async def handle_message(self, message):
        self.messages.append(message)
        return GatewayReply(
            text="reply",
            chunks=["reply"],
            conversation_key="wechat:ilink:acct:peer",
            context_id="ctx-a2a",
            task_id=None,
        )


class FakeILinkClient:
    def __init__(self) -> None:
        self.sent = []

    async def send_text(self, *, to_user_id, text, context_token, client_id=None):
        self.sent.append((to_user_id, text, context_token, client_id))
        return {"ret": 0}


async def test_ilink_runner_forwards_text_to_a2a_and_replies(tmp_path) -> None:
    store = ILinkStateStore(tmp_path)
    gateway = FakeGateway()
    ilink_client = FakeILinkClient()
    runner = ILinkGatewayRunner(
        account_id="acct",
        ilink_client=ilink_client,
        gateway=gateway,
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
    assert ilink_client.sent == [("peer", "reply", "ctx-token", None)]
