from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from a2a.client.client import ClientCallContext
from a2a.client.transports.http_helpers import get_http_args, handle_http_exceptions
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import GetTaskRequest, SendMessageRequest, StreamResponse, Task, TaskState
from google.protobuf import json_format  # type: ignore[import-untyped]
from jsonrpc.jsonrpc2 import JSONRPC20Request, JSONRPC20Response  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)
TASK_RECOVERY_POLL_INTERVAL_SECONDS = 2.0
WORKING_TASK_STATES = frozenset({"submitted", "working"})


@dataclass(frozen=True, slots=True)
class _SSEFrame:
    event: str
    data: str


class ResilientJsonRpcTransport(JsonRpcTransport):
    def __init__(
        self,
        httpx_client,
        agent_card,
        url: str,
        *,
        timeout_seconds: float,
        stream_idle_timeout_seconds: float,
    ) -> None:
        super().__init__(httpx_client, agent_card, url)
        self._timeout_seconds = timeout_seconds
        self._stream_idle_timeout_seconds = stream_idle_timeout_seconds

    async def send_message_streaming(
        self,
        request: SendMessageRequest,
        *,
        context: ClientCallContext | None = None,
    ) -> AsyncGenerator[StreamResponse]:
        rpc_request = JSONRPC20Request(
            method="SendStreamingMessage",
            params=json_format.MessageToDict(request),
            _id=str(uuid4()),
        )
        task_id: str | None = None
        task_state: str | None = None
        try:
            async for event in self._iter_stream_response_events(
                dict(rpc_request.data),
                context=context,
            ):
                state = _task_state_from_stream_response(event)
                if state is not None:
                    task_state = state
                event_task_id = _task_id_from_stream_response(event)
                if event_task_id:
                    task_id = event_task_id
                yield event
        except TimeoutError as exc:
            if not task_id or task_state not in WORKING_TASK_STATES:
                raise exc
            logger.warning(
                "A2A stream stalled while task still active; falling back to GetTask task_id=%s "
                "state=%s",
                task_id,
                task_state,
            )
            async for recovery_event in self._recover_task_events(task_id, context=context):
                yield recovery_event

    async def _iter_stream_response_events(
        self,
        rpc_request_payload: dict[str, object],
        *,
        context: ClientCallContext | None = None,
    ) -> AsyncIterator[StreamResponse]:
        http_kwargs = get_http_args(context)
        idle_timeout = _positive_float_or_none(self._stream_idle_timeout_seconds)

        with handle_http_exceptions():
            async with self.httpx_client.stream(
                "POST",
                self.url,
                json=rpc_request_payload,
                **http_kwargs,
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    content = await response.aread()
                    if not content:
                        return
                    yield _parse_stream_response_payload(content.decode("utf-8"))
                    return

                parser = _SSEFrameParser()
                line_iter = response.aiter_lines().__aiter__()
                while True:
                    try:
                        raw_line = await _next_stream_line(
                            line_iter,
                            idle_timeout=idle_timeout,
                        )
                    except StopAsyncIteration:
                        frame = parser.flush()
                        if frame is None or not frame.data:
                            return
                        if frame.event == "error":
                            self._handle_sse_error(frame.data)
                        yield _parse_stream_response_payload(frame.data)
                        return

                    frame = parser.push(raw_line.rstrip("\n"))
                    if frame is None:
                        continue
                    if not frame.data:
                        logger.debug("A2A upstream transport keepalive received")
                        continue
                    if frame.event == "error":
                        self._handle_sse_error(frame.data)
                    yield _parse_stream_response_payload(frame.data)

    async def _recover_task_events(
        self,
        task_id: str,
        *,
        context: ClientCallContext | None = None,
    ) -> AsyncGenerator[StreamResponse]:
        deadline = time.monotonic() + max(self._timeout_seconds, 0.0)
        poll_interval = min(
            TASK_RECOVERY_POLL_INTERVAL_SECONDS,
            max(self._stream_idle_timeout_seconds / 2.0, 0.25),
        )
        while True:
            task = await asyncio.wait_for(
                super().get_task(GetTaskRequest(id=task_id), context=context),
                timeout=self._timeout_seconds,
            )
            reply_state = _task_state_from_task(task)
            logger.debug(
                "A2A GetTask recovery snapshot task_id=%s context_id=%s state=%s text_chars=%s",
                task.id or None,
                task.context_id or None,
                reply_state,
                len(_text_from_task(task)),
            )
            yield _stream_response_from_task(task)
            if reply_state not in WORKING_TASK_STATES:
                return
            if self._timeout_seconds > 0 and time.monotonic() >= (deadline - 1e-9):
                raise TimeoutError(
                    f"A2A GetTask recovery timeout after {self._timeout_seconds:.1f}s"
                )
            await asyncio.sleep(poll_interval)


class _SSEFrameParser:
    def __init__(self) -> None:
        self._event = "message"
        self._data_lines: list[str] = []

    def push(self, line: str) -> _SSEFrame | None:
        if line == "":
            frame = _SSEFrame(event=self._event, data="\n".join(self._data_lines))
            self._reset()
            return frame
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value or "message"
        elif field == "data":
            self._data_lines.append(value)
        return None

    def flush(self) -> _SSEFrame | None:
        if not self._data_lines:
            self._reset()
            return None
        frame = _SSEFrame(event=self._event, data="\n".join(self._data_lines))
        self._reset()
        return frame

    def _reset(self) -> None:
        self._event = "message"
        self._data_lines = []


async def _next_stream_line(
    line_iter,
    *,
    idle_timeout: float | None,
) -> str:
    try:
        if idle_timeout is None:
            return await anext(line_iter)
        return await asyncio.wait_for(anext(line_iter), timeout=idle_timeout)
    except TimeoutError as exc:
        idle_value = idle_timeout if idle_timeout is not None else 0.0
        raise TimeoutError(f"A2A stream idle timeout after {idle_value:.1f}s") from exc


def _positive_float_or_none(value: float) -> float | None:
    return float(value) if value > 0 else None


def _parse_stream_response_payload(payload: str) -> StreamResponse:
    json_rpc_response = JSONRPC20Response.from_json(payload)
    if json_rpc_response.error:
        code = getattr(json_rpc_response.error, "code", "unknown")
        message = getattr(json_rpc_response.error, "message", "unknown error")
        raise RuntimeError(f"A2A upstream JSON-RPC error {code}: {message}")
    return cast(StreamResponse, json_format.ParseDict(json_rpc_response.result, StreamResponse()))


def _stream_response_from_task(task: Task) -> StreamResponse:
    response = StreamResponse()
    response.task.CopyFrom(task)
    return response


def _task_id_from_stream_response(response: StreamResponse) -> str | None:
    if response.HasField("task"):
        return response.task.id or None
    if response.HasField("message"):
        return response.message.task_id or None
    if response.HasField("artifact_update"):
        return response.artifact_update.task_id or None
    if response.HasField("status_update"):
        return response.status_update.task_id or None
    return None


def _task_state_from_stream_response(response: StreamResponse) -> str | None:
    if response.HasField("task"):
        return _task_state_from_task(response.task)
    if response.HasField("status_update"):
        return _task_state_to_text(response.status_update.status.state)
    return None


def _task_state_from_task(task: Task) -> str | None:
    return _task_state_to_text(task.status.state)


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


def _text_from_task(task: Task) -> str:
    artifact_parts = [part for artifact in task.artifacts for part in artifact.parts]
    text = _extract_text(artifact_parts)
    if not text and task.status.HasField("message"):
        text = _extract_text(task.status.message.parts)
    return text


def _extract_text(parts) -> str:
    chunks = [part.text for part in parts if part.text]
    return "\n".join(chunks)
