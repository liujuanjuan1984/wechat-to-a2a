from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from wechat_to_a2a.conversation import (
    ConversationStore,
    conversation_key_for_wechat,
)
from wechat_to_a2a.wechat import WeChatMessage


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def test_conversation_key_includes_wechat_account_and_user() -> None:
    message = WeChatMessage(
        to_user="gh_account",
        from_user="user-1",
        create_time=123,
        msg_type="text",
        content="hello",
    )

    assert conversation_key_for_wechat(message) == "wechat:official:gh_account:user-1"


def test_conversation_key_distinguishes_ilink_gateway() -> None:
    message = WeChatMessage(
        to_user="ilink-account",
        from_user="user-1",
        create_time=123,
        msg_type="text",
        content="hello",
        gateway="ilink",
    )

    assert conversation_key_for_wechat(message) == "wechat:ilink:ilink-account:user-1"


def test_conversation_store_persists_a2a_state(tmp_path) -> None:
    path = tmp_path / "state" / "conversations.json"
    store = ConversationStore(path)
    state = store.get_or_create(
        key="wechat:official:gh:user",
        wechat_account_id="gh",
        wechat_user_id="user",
    )

    store.update_a2a_state(key=state.key, context_id="ctx-1", task_id="task-1")

    restored = ConversationStore(path).get_or_create(
        key="wechat:official:gh:user",
        wechat_account_id="gh",
        wechat_user_id="user",
    )
    assert restored.a2a_context_id == "ctx-1"
    assert restored.a2a_task_id == "task-1"
    assert restored.wechat_account_id == "gh"
    assert restored.wechat_user_id == "user"
    assert restored.last_interaction_at


def test_conversation_store_tracks_interaction_and_expiry(tmp_path) -> None:
    clock = MutableClock(datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    store = ConversationStore(tmp_path / "state" / "conversations.json", now=clock.now)
    state = store.get_or_create(
        key="wechat:official:gh:user",
        wechat_account_id="gh",
        wechat_user_id="user",
    )

    clock.advance(timedelta(hours=6))
    assert not store.is_idle_expired(key=state.key, idle_timeout=timedelta(hours=6))

    clock.advance(timedelta(seconds=1))
    assert store.is_idle_expired(key=state.key, idle_timeout=timedelta(hours=6))

    store.touch_interaction(key=state.key)
    assert not store.is_idle_expired(key=state.key, idle_timeout=timedelta(hours=6))

    store.reset_a2a_state(key=state.key)
    reset_state = store.get(key=state.key)
    assert reset_state is not None
    assert reset_state.a2a_context_id is None
    assert reset_state.a2a_task_id is None


def test_conversation_store_uses_updated_at_for_legacy_state_files(tmp_path) -> None:
    path = tmp_path / "state" / "conversations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "conversations": {
                    "wechat:official:gh:user": {
                        "key": "wechat:official:gh:user",
                        "wechat_account_id": "gh",
                        "wechat_user_id": "user",
                        "a2a_context_id": "ctx-1",
                        "a2a_task_id": "task-1",
                        "created_at": "2026-05-09T12:00:00+00:00",
                        "updated_at": "2026-05-09T13:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    restored = ConversationStore(path).get(
        key="wechat:official:gh:user",
    )

    assert restored is not None
    assert restored.last_interaction_at == "2026-05-09T13:00:00+00:00"
