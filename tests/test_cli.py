from __future__ import annotations

import asyncio

import pytest

from wechat_to_a2a.cli import _run_ilink_gateway, _run_until_interrupted, build_parser


def test_cli_accepts_serve_command() -> None:
    args = build_parser().parse_args(["serve", "--host", "0.0.0.0", "--port", "9000"])
    assert args.command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_cli_accepts_ilink_login_command() -> None:
    args = build_parser().parse_args(["ilink-login", "--timeout", "30"])
    assert args.command == "ilink-login"
    assert args.timeout == 30


def test_cli_accepts_ilink_run_command() -> None:
    args = build_parser().parse_args(["ilink-run", "--account-id", "acct"])
    assert args.command == "ilink-run"
    assert args.account_id == "acct"


def test_cli_requires_command() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args([])
    assert exc_info.value.code == 2


async def test_run_ilink_gateway_closes_clients_on_cancellation() -> None:
    class Runner:
        async def run_forever(self) -> None:
            raise asyncio.CancelledError

    class Closable:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    a2a_client = Closable()
    ilink_client = Closable()

    with pytest.raises(asyncio.CancelledError):
        await _run_ilink_gateway(
            runner=Runner(),  # type: ignore[arg-type]
            a2a_client=a2a_client,  # type: ignore[arg-type]
            ilink_client=ilink_client,  # type: ignore[arg-type]
        )

    assert a2a_client.closed
    assert ilink_client.closed


def test_run_until_interrupted_returns_130(monkeypatch) -> None:
    async def noop() -> None:
        return None

    def raise_keyboard_interrupt(_coro) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("wechat_to_a2a.cli.asyncio.run", raise_keyboard_interrupt)
    coro = noop()

    try:
        assert _run_until_interrupted(coro) == 130
    finally:
        coro.close()
