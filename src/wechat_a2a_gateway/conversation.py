from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .wechat import WeChatMessage


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class ConversationState:
    key: str
    wechat_account_id: str
    wechat_user_id: str
    a2a_context_id: str | None = None
    a2a_task_id: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationState:
        return cls(
            key=str(data["key"]),
            wechat_account_id=str(data["wechat_account_id"]),
            wechat_user_id=str(data["wechat_user_id"]),
            a2a_context_id=_optional_str(data.get("a2a_context_id")),
            a2a_task_id=_optional_str(data.get("a2a_task_id")),
            created_at=str(data.get("created_at") or _now_iso()),
            updated_at=str(data.get("updated_at") or _now_iso()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._states: dict[str, ConversationState] = {}
        if self._path is not None:
            self._load()

    def get_or_create(
        self,
        *,
        key: str,
        wechat_account_id: str,
        wechat_user_id: str,
    ) -> ConversationState:
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = ConversationState(
                    key=key,
                    wechat_account_id=wechat_account_id,
                    wechat_user_id=wechat_user_id,
                )
                self._states[key] = state
                self._save()
            return state

    def update_a2a_state(
        self,
        *,
        key: str,
        context_id: str | None,
        task_id: str | None,
    ) -> ConversationState:
        with self._lock:
            state = self._states[key]
            state.a2a_context_id = context_id
            state.a2a_task_id = task_id
            state.updated_at = _now_iso()
            self._save()
            return state

    def _load(self) -> None:
        assert self._path is not None
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"invalid conversation state file: {self._path}")
        conversations = data.get("conversations", data)
        if not isinstance(conversations, dict):
            raise ValueError(f"invalid conversation state file: {self._path}")
        self._states = {
            str(key): ConversationState.from_dict(value)
            for key, value in conversations.items()
            if isinstance(value, dict)
        }

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {
            "version": 1,
            "conversations": {key: state.to_dict() for key, state in sorted(self._states.items())},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_name(f".{self._path.name}.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self._path)


def conversation_key_for_wechat(message: WeChatMessage) -> str:
    return f"wechat:official:{message.to_user}:{message.from_user}"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
