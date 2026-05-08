from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterable
from contextlib import suppress
from dataclasses import dataclass
from uuid import uuid4

import httpx
from a2a.client import Client, ClientConfig, ClientFactory
from a2a.client.card_resolver import parse_agent_card
from a2a.client.client_factory import TransportProtocol
from a2a.types import Part, Role, SendMessageRequest, StreamResponse, Task, TaskState

logger = logging.getLogger(__name__)
STREAM_HEARTBEAT_INTERVAL_SECONDS = 15.0

TURN_TERMINAL_STATES = frozenset(
    {
        "auth-required",
        "canceled",
        "completed",
        "failed",
        "input-required",
        "rejected",
    }
)


@dataclass(frozen=True, slots=True)
class A2AReply:
    text: str
    context_id: str | None
    task_id: str | None
    state: str | None


@dataclass(frozen=True, slots=True)
class _SDKClientEntry:
    client: Client
    streaming: bool


class A2AClient:
    def __init__(
        self,
        *,
        agent_card_url: str,
        bearer_token: str | None = None,
        timeout_seconds: float = 300.0,
        stream_idle_timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._agent_card_url = agent_card_url
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds
        self._stream_idle_timeout_seconds = stream_idle_timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._sdk_client: _SDKClientEntry | None = None

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

        logger.info(
            "A2A send_message start mode=%s message_id=%s input_chars=%s has_context=%s "
            "has_task=%s",
            "streaming" if sdk_client.streaming else "non-streaming",
            request.message.message_id,
            len(text),
            bool(context_id),
            bool(task_id),
        )
        accumulator = _StreamAccumulator()
        async for event in self._iter_events_with_timeouts(
            sdk_client.client.send_message(request),
            streaming=sdk_client.streaming,
        ):
            if event is None:
                logger.debug("A2A upstream stream heartbeat")
                continue
            accumulator.consume(event)
            logger.info("A2A event consumed %s", accumulator.last_event_summary())
            if accumulator.state in TURN_TERMINAL_STATES:
                break

        reply = accumulator.reply()
        if reply is None:
            logger.warning("A2A send_message returned no response events=%s", accumulator.summary())
            raise RuntimeError("A2A send_message returned no response")
        if not reply.text:
            logger.warning("A2A upstream reply contained no text %s", accumulator.summary())
        else:
            logger.info(
                "A2A send_message completed text_chars=%s context_id=%s task_id=%s state=%s "
                "events=%s",
                len(reply.text),
                reply.context_id,
                reply.task_id,
                reply.state,
                accumulator.event_count,
            )
        return reply

    async def _get_sdk_client(self) -> _SDKClientEntry:
        if self._sdk_client is not None:
            return self._sdk_client

        httpx_client = self._httpx_client()
        config = ClientConfig(
            streaming=True,
            polling=False,
            httpx_client=httpx_client,
            supported_protocol_bindings=[TransportProtocol.JSONRPC],
            accepted_output_modes=["text/plain"],
        )
        factory = ClientFactory(config)
        card = await self._fetch_agent_card(httpx_client)
        entry = _SDKClientEntry(
            client=factory.create(card),
            streaming=bool(card.capabilities.streaming),
        )
        logger.info(
            "A2A agent card loaded name=%r version=%r streaming_declared=%s "
            "selected_mode=%s interfaces=%s",
            card.name,
            card.version,
            bool(card.capabilities.streaming),
            "streaming" if entry.streaming else "non-streaming",
            [
                {
                    "protocol": interface.protocol_binding,
                    "version": interface.protocol_version,
                    "url": interface.url,
                }
                for interface in card.supported_interfaces
            ],
        )
        self._sdk_client = entry
        return entry

    async def _fetch_agent_card(self, httpx_client: httpx.AsyncClient):
        logger.info("A2A fetching agent card url=%s", self._agent_card_url)
        response = await asyncio.wait_for(
            httpx_client.get(self._agent_card_url),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        card = response.json()
        if not isinstance(card, dict):
            raise RuntimeError(f"unexpected A2A agent card shape: {card!r}")
        return parse_agent_card(card)

    def _httpx_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            client = self._client
        else:
            timeout = httpx.Timeout(
                connect=self._timeout_seconds,
                read=None,
                write=self._timeout_seconds,
                pool=self._timeout_seconds,
            )
            client = httpx.AsyncClient(timeout=timeout)
            self._client = client
        if self._bearer_token:
            client.headers["Authorization"] = f"Bearer {self._bearer_token}"
        return client

    async def aclose(self) -> None:
        if not self._owns_client:
            return
        if self._sdk_client is not None:
            close = getattr(self._sdk_client.client, "close", None)
            if callable(close):
                await close()
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _iter_events_with_timeouts(
        self,
        stream: AsyncIterator[StreamResponse],
        *,
        streaming: bool,
    ) -> AsyncIterator[StreamResponse | None]:
        started_at = time.monotonic()
        last_activity_at = started_at
        total_timeout = None if streaming else _positive_float_or_none(self._timeout_seconds)
        idle_timeout = (
            _positive_float_or_none(self._stream_idle_timeout_seconds) if streaming else None
        )
        heartbeat_interval = STREAM_HEARTBEAT_INTERVAL_SECONDS if streaming else None
        stream_iter = _iter_stream_events_with_heartbeat(
            stream,
            heartbeat_interval_seconds=heartbeat_interval or 0.0,
        ).__aiter__()

        while True:
            now = time.monotonic()
            if total_timeout is not None and (now - started_at) >= (total_timeout - 1e-9):
                raise TimeoutError(f"A2A stream total timeout after {total_timeout:.1f}s")

            wait_timeout = _next_wait_timeout(
                now=now,
                started_at=started_at,
                last_activity_at=last_activity_at,
                total_timeout=total_timeout,
                idle_timeout=idle_timeout,
            )
            try:
                if wait_timeout is None:
                    event = await anext(stream_iter)
                else:
                    event = await asyncio.wait_for(anext(stream_iter), timeout=wait_timeout)
            except StopAsyncIteration:
                return
            except TimeoutError as exc:
                elapsed = time.monotonic() - started_at
                if total_timeout is not None and elapsed >= (total_timeout - 1e-9):
                    raise TimeoutError(
                        f"A2A stream total timeout after {total_timeout:.1f}s"
                    ) from exc
                idle_value = idle_timeout if idle_timeout is not None else 0.0
                raise TimeoutError(f"A2A stream idle timeout after {idle_value:.1f}s") from exc

            last_activity_at = time.monotonic()
            yield event


class _StreamAccumulator:
    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._final_text: str | None = None
        self._event_kinds: list[str] = []
        self._last_event: dict[str, object] = {}
        self.context_id: str | None = None
        self.task_id: str | None = None
        self.state: str | None = None

    @property
    def event_count(self) -> int:
        return len(self._event_kinds)

    def consume(self, response: StreamResponse) -> None:
        if response.HasField("task"):
            self._consume_task(response.task)
            return
        if response.HasField("message"):
            self._consume_message_response(response)
            return
        if response.HasField("artifact_update"):
            self._consume_artifact_update_response(response)
            return
        if response.HasField("status_update"):
            self._consume_status_update_response(response)
            return
        raise RuntimeError(f"unexpected A2A response shape: {response!r}")

    def reply(self) -> A2AReply | None:
        text = self._final_text if self._final_text is not None else "\n".join(self._chunks)
        if not text and not (self.context_id or self.task_id or self.state):
            return None
        return A2AReply(
            text=text,
            context_id=self.context_id,
            task_id=self.task_id,
            state=self.state,
        )

    def last_event_summary(self) -> dict[str, object]:
        return dict(self._last_event)

    def summary(self) -> dict[str, object]:
        text = self._final_text if self._final_text is not None else "\n".join(self._chunks)
        return {
            "events": self.event_count,
            "event_kinds": list(self._event_kinds),
            "text_chars": len(text),
            "chunk_count": len(self._chunks),
            "final_text_chars": len(self._final_text or ""),
            "context_id": self.context_id,
            "task_id": self.task_id,
            "state": self.state,
            "last_event": dict(self._last_event),
        }

    def _consume_task(self, task: Task) -> None:
        reply = _reply_from_task(task)
        self._final_text = reply.text
        self.context_id = reply.context_id or self.context_id
        self.task_id = reply.task_id or self.task_id
        self.state = reply.state or self.state
        self._record_event(
            "task",
            text_chars=len(reply.text),
            artifact_count=len(task.artifacts),
            status_has_message=task.status.HasField("message"),
        )

    def _consume_message_response(self, response: StreamResponse) -> None:
        reply = _reply_from_stream_response(response)
        if reply.text:
            self._chunks.append(reply.text)
        self.context_id = reply.context_id or self.context_id
        self.task_id = reply.task_id or self.task_id
        self.state = reply.state or self.state
        self._record_event("message", text_chars=len(reply.text))

    def _consume_artifact_update_response(self, response: StreamResponse) -> None:
        update = response.artifact_update
        text = _extract_text(update.artifact.parts)
        if text:
            self._chunks.append(text)
        self.context_id = update.context_id or self.context_id
        self.task_id = update.task_id or self.task_id
        self._record_event(
            "artifact_update",
            text_chars=len(text),
            part_count=len(update.artifact.parts),
            append=update.append,
            last_chunk=update.last_chunk,
        )

    def _consume_status_update_response(self, response: StreamResponse) -> None:
        update = response.status_update
        text = ""
        if update.status.HasField("message"):
            text = _extract_text(update.status.message.parts)
        if text:
            self._chunks.append(text)
        self.context_id = update.context_id or self.context_id
        self.task_id = update.task_id or self.task_id
        self.state = _task_state_to_text(update.status.state) or self.state
        self._record_event(
            "status_update",
            text_chars=len(text),
            status_has_message=update.status.HasField("message"),
        )

    def _record_event(self, kind: str, **extra: object) -> None:
        self._event_kinds.append(kind)
        self._last_event = {
            "kind": kind,
            "context_id": self.context_id,
            "task_id": self.task_id,
            "state": self.state,
            **extra,
        }


async def _iter_stream_events_with_heartbeat(
    stream: AsyncIterator[StreamResponse],
    *,
    heartbeat_interval_seconds: float,
) -> AsyncIterator[StreamResponse | None]:
    stream_iter = stream.__aiter__()

    async def _next_stream_event() -> StreamResponse:
        return await stream_iter.__anext__()

    next_event_task = asyncio.create_task(_next_stream_event())
    try:
        while True:
            if heartbeat_interval_seconds > 0:
                done, _ = await asyncio.wait(
                    {next_event_task},
                    timeout=heartbeat_interval_seconds,
                )
                if not done:
                    yield None
                    continue

            try:
                event = await next_event_task
            except StopAsyncIteration:
                return

            next_event_task = asyncio.create_task(_next_stream_event())
            yield event
    finally:
        if not next_event_task.done():
            next_event_task.cancel()
            with suppress(asyncio.CancelledError):
                await next_event_task
        else:
            with suppress(asyncio.CancelledError):
                next_event_task.exception()


def _positive_float_or_none(value: float) -> float | None:
    return float(value) if value > 0 else None


def _next_wait_timeout(
    *,
    now: float,
    started_at: float,
    last_activity_at: float,
    total_timeout: float | None,
    idle_timeout: float | None,
) -> float | None:
    wait_timeout = None
    if idle_timeout is not None:
        wait_timeout = max(idle_timeout - (now - last_activity_at), 0.0)
    if total_timeout is not None:
        remaining_total = max(total_timeout - (now - started_at), 0.0)
        wait_timeout = (
            min(wait_timeout, remaining_total) if wait_timeout is not None else remaining_total
        )
    return wait_timeout


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
