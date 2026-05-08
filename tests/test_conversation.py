from __future__ import annotations

from wechat_a2a_gateway.conversation import (
    ConversationStore,
    conversation_key_for_wechat,
)
from wechat_a2a_gateway.wechat import WeChatMessage


def test_conversation_key_includes_wechat_account_and_user() -> None:
    message = WeChatMessage(
        to_user="gh_account",
        from_user="user-1",
        create_time=123,
        msg_type="text",
        content="hello",
    )

    assert conversation_key_for_wechat(message) == "wechat:official:gh_account:user-1"


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
