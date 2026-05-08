from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .a2a_client import A2AReply
from .conversation import ConversationStore, conversation_key_for_wechat
from .formatting import MAX_WECHAT_TEXT_CHARS, split_wechat_text
from .wechat import WeChatMessage

CONTINUATION_STATES = frozenset({"auth-required", "input-required", "working"})


class A2AClientProtocol(Protocol):
    async def send_message(
        self,
        *,
        text: str,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> A2AReply: ...


@dataclass(frozen=True, slots=True)
class GatewayReply:
    text: str
    chunks: list[str]
    conversation_key: str
    context_id: str | None
    task_id: str | None


class WeChatA2AGateway:
    def __init__(
        self,
        *,
        a2a_client: A2AClientProtocol,
        conversation_store: ConversationStore,
        reply_max_chars: int = MAX_WECHAT_TEXT_CHARS,
        split_multiline_messages: bool = False,
    ) -> None:
        self._a2a_client = a2a_client
        self._conversation_store = conversation_store
        self._reply_max_chars = reply_max_chars
        self._split_multiline_messages = split_multiline_messages

    async def handle_message(self, message: WeChatMessage) -> GatewayReply:
        conversation_key = conversation_key_for_wechat(message)
        state = self._conversation_store.get_or_create(
            key=conversation_key,
            wechat_account_id=message.to_user,
            wechat_user_id=message.from_user,
        )
        a2a_reply = await self._a2a_client.send_message(
            text=message.content,
            context_id=state.a2a_context_id,
            task_id=state.a2a_task_id,
        )

        context_id = a2a_reply.context_id or state.a2a_context_id
        task_id = a2a_reply.task_id if a2a_reply.state in CONTINUATION_STATES else None
        self._conversation_store.update_a2a_state(
            key=conversation_key,
            context_id=context_id,
            task_id=task_id,
        )

        chunks = split_wechat_text(
            a2a_reply.text,
            max_chars=self._reply_max_chars,
            split_multiline_messages=self._split_multiline_messages,
        )
        text = "\n\n".join(chunks) if chunks else "The upstream A2A agent returned no text."
        return GatewayReply(
            text=text,
            chunks=chunks,
            conversation_key=conversation_key,
            context_id=context_id,
            task_id=task_id,
        )
