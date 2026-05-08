from __future__ import annotations

import httpx
import pytest

from wechat_a2a_gateway.a2a_client import A2AClient


@pytest.mark.asyncio
async def test_send_message_extracts_artifact_text_and_context() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b"SendMessage" in payload
        assert request.headers["authorization"] == "Bearer token"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "result": {
                    "id": "task-1",
                    "contextId": "ctx-1",
                    "status": {"state": "completed"},
                    "artifacts": [{"parts": [{"type": "text", "text": "hello back"}]}],
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(
            endpoint="https://agent.example/a2a",
            bearer_token="token",
            client=http_client,
        )
        reply = await client.send_message(text="hello")

    assert reply.text == "hello back"
    assert reply.context_id == "ctx-1"
    assert reply.task_id == "task-1"
    assert reply.state == "completed"


@pytest.mark.asyncio
async def test_send_message_raises_on_jsonrpc_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "error": {"code": -32603, "message": "failed"},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(endpoint="https://agent.example/a2a", client=http_client)
        with pytest.raises(RuntimeError, match="A2A JSON-RPC error"):
            await client.send_message(text="hello")
