from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .wechat import WeChatMessage

TimestampProvider = Callable[[], datetime]


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
    last_interaction_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        default_timestamp: str | None = None,
    ) -> ConversationState:
        fallback = default_timestamp or _now_iso()
        created_at = str(data.get("created_at") or fallback)
        updated_at = str(data.get("updated_at") or created_at)
        last_interaction_at = str(
            data.get("last_interaction_at") or data.get("updated_at") or created_at
        )
        return cls(
            key=str(data["key"]),
            wechat_account_id=str(data["wechat_account_id"]),
            wechat_user_id=str(data["wechat_user_id"]),
            a2a_context_id=_optional_str(data.get("a2a_context_id")),
            a2a_task_id=_optional_str(data.get("a2a_task_id")),
            created_at=created_at,
            updated_at=updated_at,
            last_interaction_at=last_interaction_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        now: TimestampProvider | None = None,
    ) -> None:
        self._path = path
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._states: dict[str, ConversationState] = {}
        if self._path is not None:
            if self._path.exists():
                self._load()
            else:
                self._save()

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
                timestamp = self._now_iso()
                state = ConversationState(
                    key=key,
                    wechat_account_id=wechat_account_id,
                    wechat_user_id=wechat_user_id,
                    created_at=timestamp,
                    updated_at=timestamp,
                    last_interaction_at=timestamp,
                )
                self._states[key] = state
                self._save()
            return state

    def get(self, *, key: str) -> ConversationState | None:
        with self._lock:
            return self._states.get(key)

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
            state.updated_at = self._now_iso()
            self._save()
            return state

    def reset_a2a_state(self, *, key: str) -> ConversationState:
        with self._lock:
            state = self._states[key]
            state.a2a_context_id = None
            state.a2a_task_id = None
            state.updated_at = self._now_iso()
            self._save()
            return state

    def touch_interaction(self, *, key: str) -> ConversationState:
        with self._lock:
            state = self._states[key]
            timestamp = self._now_iso()
            state.last_interaction_at = timestamp
            state.updated_at = timestamp
            self._save()
            return state

    def is_idle_expired(self, *, key: str, idle_timeout: timedelta) -> bool:
        if idle_timeout <= timedelta(0):
            return False
        with self._lock:
            state = self._states[key]
            last_interaction_at = _parse_datetime(state.last_interaction_at)
            if last_interaction_at is None:
                return False
            return self._now() - last_interaction_at > idle_timeout

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
        default_timestamp = self._now_iso()
        self._states = {
            str(key): ConversationState.from_dict(value, default_timestamp=default_timestamp)
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

    def _now_iso(self) -> str:
        return self._now().isoformat()


def conversation_key_for_wechat(message: WeChatMessage) -> str:
    return f"wechat:{message.gateway}:{message.to_user}:{message.from_user}"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _parse_datetime(value: str) -> datetime | None:
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
