from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import httpx


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
        if not self._endpoint and not self._agent_card_url:
            raise ValueError("agent_card_url or endpoint is required")

    async def send_message(
        self,
        *,
        text: str,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> A2AReply:
        endpoint = await self._resolve_endpoint()
        headers = self._headers(content_type="application/json")

        message: dict[str, Any] = {
            "role": "user",
            "parts": [{"type": "text", "text": text}],
        }
        if context_id:
            message["contextId"] = context_id
        if task_id:
            message["taskId"] = task_id

        payload = {
            "jsonrpc": "2.0",
            "id": "wechat-to-a2a",
            "method": "SendMessage",
            "params": {"message": message},
        }

        if self._client is not None:
            response = await self._client.post(endpoint, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(f"A2A JSON-RPC error: {body['error']!r}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"unexpected A2A response shape: {body!r}")
        return _reply_from_task(result)

    async def _resolve_endpoint(self) -> str:
        if self._endpoint:
            return self._endpoint
        assert self._agent_card_url is not None
        if self._client is not None:
            response = await self._client.get(
                self._agent_card_url,
                headers=self._headers(),
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    self._agent_card_url,
                    headers=self._headers(),
                )
        response.raise_for_status()
        card = response.json()
        if not isinstance(card, dict):
            raise RuntimeError(f"unexpected A2A agent card shape: {card!r}")
        endpoint = _optional_str(card.get("url"))
        if not endpoint:
            raise RuntimeError(f"A2A agent card missing url: {card!r}")
        self._endpoint = endpoint
        return endpoint

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers


def _reply_from_task(task: dict[str, Any]) -> A2AReply:
    context_id = _optional_str(task.get("contextId"))
    task_id = _optional_str(task.get("id") or task.get("taskId"))
    status = task.get("status") if isinstance(task.get("status"), dict) else {}
    state = _optional_str(status.get("state")) if isinstance(status, dict) else None

    artifact_parts = list(
        itertools.chain.from_iterable(
            artifact.get("parts", [])
            for artifact in task.get("artifacts", [])
            if isinstance(artifact, dict)
        )
    )
    text = _extract_text(artifact_parts)
    if not text and isinstance(status, dict):
        message = status.get("message")
        if isinstance(message, dict):
            text = _extract_text(message.get("parts", []))
    return A2AReply(text=text, context_id=context_id, task_id=task_id, state=state)


def _extract_text(parts: object) -> str:
    if not isinstance(parts, list):
        return ""
    chunks = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    ]
    return "\n".join(chunk for chunk in chunks if chunk)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
