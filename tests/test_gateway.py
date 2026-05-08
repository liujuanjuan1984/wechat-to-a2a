from __future__ import annotations

from wechat_a2a_gateway.a2a_client import A2AReply
from wechat_a2a_gateway.conversation import ConversationStore
from wechat_a2a_gateway.gateway import WeChatA2AGateway
from wechat_a2a_gateway.wechat import WeChatMessage


class FakeA2AClient:
    def __init__(self, replies: list[A2AReply]) -> None:
        self.replies = replies
        self.calls: list[tuple[str, str | None, str | None]] = []

    async def send_message(
        self,
        *,
        text: str,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> A2AReply:
        self.calls.append((text, context_id, task_id))
        return self.replies.pop(0)


def _message(content: str = "hello") -> WeChatMessage:
    return WeChatMessage(
        to_user="gh_x",
        from_user="user-1",
        create_time=123,
        msg_type="text",
        content=content,
    )


async def test_gateway_reuses_context_across_wechat_messages() -> None:
    client = FakeA2AClient(
        [
            A2AReply(text="first", context_id="ctx-1", task_id="task-1", state="completed"),
            A2AReply(text="second", context_id="ctx-1", task_id="task-2", state="completed"),
        ]
    )
    gateway = WeChatA2AGateway(a2a_client=client, conversation_store=ConversationStore())

    first = await gateway.handle_message(_message("first input"))
    second = await gateway.handle_message(_message("second input"))

    assert first.text == "first"
    assert second.text == "second"
    assert client.calls == [
        ("first input", None, None),
        ("second input", "ctx-1", None),
    ]


async def test_gateway_reuses_task_id_for_input_required_continuation() -> None:
    client = FakeA2AClient(
        [
            A2AReply(
                text="Need more info",
                context_id="ctx-1",
                task_id="task-1",
                state="input-required",
            ),
            A2AReply(text="done", context_id="ctx-1", task_id="task-1", state="completed"),
        ]
    )
    gateway = WeChatA2AGateway(a2a_client=client, conversation_store=ConversationStore())

    first = await gateway.handle_message(_message("start"))
    second = await gateway.handle_message(_message("details"))

    assert first.task_id == "task-1"
    assert second.task_id is None
    assert client.calls == [
        ("start", None, None),
        ("details", "ctx-1", "task-1"),
    ]
