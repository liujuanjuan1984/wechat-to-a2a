from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import uuid4

import httpx
from a2a.client import Client, ClientConfig, ClientFactory, minimal_agent_card
from a2a.client.card_resolver import parse_agent_card
from a2a.client.client_factory import TransportProtocol
from a2a.types import Part, Role, SendMessageRequest, StreamResponse, Task, TaskState


@dataclass(frozen=True, slots=True)
class A2AReply:
    text: str
    context_id: str | None
    task_id: str | None
    state: str | None


class A2AClient:
    def __init__(
        self,
        *,
        agent_card_url: str | None = None,
        endpoint: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._agent_card_url = agent_card_url
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds
        self._client = client
        self._sdk_client: Client | None = None
        if not self._endpoint and not self._agent_card_url:
            raise ValueError("agent_card_url or endpoint is required")

    async def send_message(
        self,
        *,
        text: str,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> A2AReply:
        sdk_client = await self._get_sdk_client()
        request = SendMessageRequest()
        request.message.message_id = uuid4().hex
        request.message.role = Role.ROLE_USER
        request.message.parts.append(Part(text=text))
        if context_id:
            request.message.context_id = context_id
        if task_id:
            request.message.task_id = task_id

        latest: StreamResponse | None = None
        async for event in sdk_client.send_message(request):
            latest = event
        if latest is None:
            raise RuntimeError("A2A send_message returned no response")
        return _reply_from_stream_response(latest)

    async def _get_sdk_client(self) -> Client:
        if self._sdk_client is not None:
            return self._sdk_client

        httpx_client = self._httpx_client()
        config = ClientConfig(
            streaming=False,
            httpx_client=httpx_client,
            supported_protocol_bindings=[TransportProtocol.JSONRPC],
            accepted_output_modes=["text/plain"],
        )
        factory = ClientFactory(config)
        if self._endpoint:
            card = minimal_agent_card(self._endpoint, [TransportProtocol.JSONRPC])
        else:
            card = await self._fetch_agent_card(httpx_client)
        self._sdk_client = factory.create(card)
        return self._sdk_client

    async def _fetch_agent_card(self, httpx_client: httpx.AsyncClient):
        assert self._agent_card_url is not None
        response = await httpx_client.get(self._agent_card_url)
        response.raise_for_status()
        card = response.json()
        if not isinstance(card, dict):
            raise RuntimeError(f"unexpected A2A agent card shape: {card!r}")
        return parse_agent_card(card)

    def _httpx_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            client = self._client
        else:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            self._client = client
        if self._bearer_token:
            client.headers["Authorization"] = f"Bearer {self._bearer_token}"
        return client


def _reply_from_stream_response(response: StreamResponse) -> A2AReply:
    if response.HasField("task"):
        return _reply_from_task(response.task)
    if response.HasField("message"):
        return A2AReply(
            text=_extract_text(response.message.parts),
            context_id=response.message.context_id or None,
            task_id=response.message.task_id or None,
            state=None,
        )
    raise RuntimeError(f"unexpected A2A response shape: {response!r}")


def _reply_from_task(task: Task) -> A2AReply:
    artifact_parts = [part for artifact in task.artifacts for part in artifact.parts]
    text = _extract_text(artifact_parts)
    if not text and task.status.HasField("message"):
        text = _extract_text(task.status.message.parts)
    return A2AReply(
        text=text,
        context_id=task.context_id or None,
        task_id=task.id or None,
        state=_task_state_to_text(task.status.state),
    )


def _extract_text(parts: Iterable[Part]) -> str:
    chunks = [part.text for part in parts if part.text]
    return "\n".join(chunks)


def _task_state_to_text(state: int) -> str | None:
    if state == TaskState.TASK_STATE_COMPLETED:
        return "completed"
    if state == TaskState.TASK_STATE_INPUT_REQUIRED:
        return "input-required"
    if state == TaskState.TASK_STATE_AUTH_REQUIRED:
        return "auth-required"
    if state == TaskState.TASK_STATE_WORKING:
        return "working"
    if state == TaskState.TASK_STATE_SUBMITTED:
        return "submitted"
    if state == TaskState.TASK_STATE_FAILED:
        return "failed"
    if state == TaskState.TASK_STATE_CANCELED:
        return "canceled"
    if state == TaskState.TASK_STATE_REJECTED:
        return "rejected"
    return None
