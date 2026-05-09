from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from wechat_to_a2a.a2a_client import A2AReply
from wechat_to_a2a.conversation import ConversationStore
from wechat_to_a2a.gateway import WeChatA2AGateway
from wechat_to_a2a.wechat import WeChatMessage


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class FakeA2AClient:
    def __init__(self, outcomes: list[A2AReply | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, str | None, str | None]] = []

    async def send_message(
        self,
        *,
        text: str,
        context_id: str | None = None,
        task_id: str | None = None,
        on_response_started: Callable[[], Awaitable[None] | None] | None = None,
    ) -> A2AReply:
        self.calls.append((text, context_id, task_id))
        if on_response_started is not None:
            result = on_response_started()
            if result is not None:
                await result
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


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


async def test_gateway_does_not_reset_at_exactly_six_hours_but_resets_afterwards() -> None:
    clock = MutableClock(datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    store = ConversationStore(now=clock.now)
    client = FakeA2AClient(
        [
            A2AReply(text="first", context_id="ctx-1", task_id="task-1", state="completed"),
            A2AReply(text="second", context_id="ctx-1", task_id="task-2", state="completed"),
            A2AReply(text="third", context_id="ctx-2", task_id="task-3", state="completed"),
        ]
    )
    gateway = WeChatA2AGateway(a2a_client=client, conversation_store=store)

    await gateway.handle_message(_message("first input"))

    clock.advance(timedelta(hours=6))
    await gateway.handle_message(_message("second input"))

    clock.advance(timedelta(hours=6, seconds=1))
    await gateway.handle_message(_message("third input"))

    assert client.calls == [
        ("first input", None, None),
        ("second input", "ctx-1", None),
        ("third input", None, None),
    ]


async def test_gateway_reset_command_starts_new_conversation_without_upstream_call() -> None:
    client = FakeA2AClient(
        [
            A2AReply(text="first", context_id="ctx-1", task_id="task-1", state="completed"),
            A2AReply(text="second", context_id="ctx-2", task_id="task-2", state="completed"),
        ]
    )
    gateway = WeChatA2AGateway(a2a_client=client, conversation_store=ConversationStore())

    first = await gateway.handle_message(_message("first input"))
    reset = await gateway.handle_message(_message("  /reset \n"))
    second = await gateway.handle_message(_message("second input"))

    assert first.text == "first"
    assert reset.text == "Started a new conversation."
    assert second.text == "second"
    assert client.calls == [
        ("first input", None, None),
        ("second input", None, None),
    ]


async def test_gateway_does_not_treat_non_reset_text_as_local_command() -> None:
    client = FakeA2AClient(
        [A2AReply(text="reply", context_id="ctx-1", task_id="task-1", state="completed")]
    )
    gateway = WeChatA2AGateway(a2a_client=client, conversation_store=ConversationStore())

    reply = await gateway.handle_message(_message("please /reset now"))

    assert reply.text == "reply"
    assert client.calls == [("please /reset now", None, None)]


async def test_gateway_counts_inbound_interaction_even_when_upstream_fails() -> None:
    clock = MutableClock(datetime(2026, 5, 9, 12, 0, tzinfo=UTC))
    store = ConversationStore(now=clock.now)
    client = FakeA2AClient(
        [
            A2AReply(text="first", context_id="ctx-1", task_id="task-1", state="completed"),
            RuntimeError("upstream failed"),
            A2AReply(text="third", context_id="ctx-1", task_id="task-2", state="completed"),
        ]
    )
    gateway = WeChatA2AGateway(a2a_client=client, conversation_store=store)

    await gateway.handle_message(_message("first input"))

    clock.advance(timedelta(hours=5, minutes=59))
    try:
        await gateway.handle_message(_message("second input"))
    except RuntimeError as exc:
        assert str(exc) == "upstream failed"
    else:  # pragma: no cover
        raise AssertionError("expected upstream failure")

    clock.advance(timedelta(minutes=2))
    await gateway.handle_message(_message("third input"))

    assert client.calls == [
        ("first input", None, None),
        ("second input", "ctx-1", None),
        ("third input", "ctx-1", None),
    ]
