from __future__ import annotations

import httpx
import pytest

from wechat_to_a2a.a2a_client import A2AClient, _task_state_to_text


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
                    "task": {
                        "id": "task-1",
                        "contextId": "ctx-1",
                        "status": {"state": "TASK_STATE_COMPLETED"},
                        "artifacts": [{"parts": [{"text": "hello back"}]}],
                    },
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
async def test_send_message_resolves_endpoint_from_agent_card() -> None:
    seen_card_request = False
    seen_message_request = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_card_request, seen_message_request
        assert request.headers["authorization"] == "Bearer token"
        if request.url.path == "/.well-known/agent-card.json":
            seen_card_request = True
            return httpx.Response(
                200,
                json={
                    "name": "agent",
                    "description": "test agent",
                    "supportedInterfaces": [
                        {
                            "url": "https://agent.example/a2a",
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                        }
                    ],
                    "version": "1.0.0",
                    "capabilities": {},
                    "defaultInputModes": ["text/plain"],
                    "defaultOutputModes": ["text/plain"],
                },
            )
        seen_message_request = True
        assert request.url.path == "/a2a"
        assert b"SendMessage" in request.read()
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "result": {
                    "task": {
                        "id": "task-1",
                        "contextId": "ctx-1",
                        "status": {"state": "TASK_STATE_COMPLETED"},
                        "artifacts": [],
                    },
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(
            agent_card_url="https://agent.example/.well-known/agent-card.json",
            bearer_token="token",
            client=http_client,
        )
        await client.send_message(text="hello")

    assert seen_card_request
    assert seen_message_request


@pytest.mark.asyncio
async def test_send_message_resolves_endpoint_from_supported_interfaces() -> None:
    seen_card_request = False
    seen_message_request = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_card_request, seen_message_request
        if request.url.path == "/api/a2a/.well-known/agent-card.json":
            seen_card_request = True
            return httpx.Response(
                200,
                json={
                    "name": "agent",
                    "description": "test agent",
                    "supportedInterfaces": [
                        {
                            "url": "https://commons.kalos.art/api/a2a/",
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                        }
                    ],
                    "version": "1.0.0",
                    "capabilities": {},
                    "defaultInputModes": ["text/plain"],
                    "defaultOutputModes": ["text/plain"],
                },
            )
        seen_message_request = True
        assert str(request.url) == "https://commons.kalos.art/api/a2a/"
        assert b"SendMessage" in request.read()
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "result": {
                    "task": {
                        "id": "task-1",
                        "contextId": "ctx-1",
                        "status": {"state": "TASK_STATE_COMPLETED"},
                        "artifacts": [],
                    },
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(
            agent_card_url="https://commons.kalos.art/api/a2a/.well-known/agent-card.json",
            client=http_client,
        )
        await client.send_message(text="hello")

    assert seen_card_request
    assert seen_message_request


@pytest.mark.asyncio
async def test_send_message_extracts_text_from_message_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "result": {
                    "message": {
                        "messageId": "message-1",
                        "contextId": "ctx-1",
                        "role": "ROLE_AGENT",
                        "parts": [{"text": "message reply"}],
                    },
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(endpoint="https://agent.example/a2a", client=http_client)
        reply = await client.send_message(text="hello")

    assert reply.text == "message reply"
    assert reply.context_id == "ctx-1"
    assert reply.task_id is None
    assert reply.state is None


@pytest.mark.asyncio
async def test_send_message_extracts_status_message_for_input_required() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "result": {
                    "task": {
                        "id": "task-1",
                        "contextId": "ctx-1",
                        "status": {
                            "state": "TASK_STATE_INPUT_REQUIRED",
                            "message": {
                                "messageId": "message-1",
                                "role": "ROLE_AGENT",
                                "parts": [{"text": "Need more detail"}],
                            },
                        },
                    },
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(endpoint="https://agent.example/a2a", client=http_client)
        reply = await client.send_message(text="hello")

    assert reply.text == "Need more detail"
    assert reply.context_id == "ctx-1"
    assert reply.task_id == "task-1"
    assert reply.state == "input-required"


@pytest.mark.asyncio
async def test_send_message_includes_context_and_task_for_continuation() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b'"contextId":"ctx-1"' in payload
        assert b'"taskId":"task-1"' in payload
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "wechat-to-a2a",
                "result": {
                    "task": {
                        "id": "task-1",
                        "contextId": "ctx-1",
                        "status": {"state": "TASK_STATE_COMPLETED"},
                        "artifacts": [],
                    },
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(endpoint="https://agent.example/a2a", client=http_client)
        await client.send_message(text="details", context_id="ctx-1", task_id="task-1")


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
        with pytest.raises(Exception, match="failed"):
            await client.send_message(text="hello")


@pytest.mark.asyncio
async def test_send_message_raises_on_invalid_agent_card_shape() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "a", "card"])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = A2AClient(
            agent_card_url="https://agent.example/.well-known/agent-card.json",
            client=http_client,
        )
        with pytest.raises(RuntimeError, match="unexpected A2A agent card shape"):
            await client.send_message(text="hello")


def test_task_state_to_text_maps_known_states() -> None:
    assert _task_state_to_text(2) == "working"
    assert _task_state_to_text(4) == "failed"
    assert _task_state_to_text(5) == "canceled"
    assert _task_state_to_text(7) == "rejected"
    assert _task_state_to_text(999) is None
