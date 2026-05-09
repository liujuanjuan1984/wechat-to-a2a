from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wechat_to_a2a.cli import (
    _load_settings,
    _run_ilink_gateway,
    _run_until_interrupted,
    build_parser,
)


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


def test_cli_accepts_upstream_a2a_card_url_option() -> None:
    args = build_parser().parse_args(
        [
            "ilink-run",
            "--upstream-a2a-card-url",
            "https://agent.example/.well-known/agent-card.json",
        ]
    )
    assert args.upstream_a2a_card_url == "https://agent.example/.well-known/agent-card.json"


def test_cli_accepts_config_set_upstream_command() -> None:
    args = build_parser().parse_args(
        [
            "config",
            "set-upstream",
            "--card-url",
            "https://agent.example/.well-known/agent-card.json",
            "--bearer-token",
            "secret",
        ]
    )
    assert args.command == "config"
    assert args.config_command == "set-upstream"
    assert args.card_url == "https://agent.example/.well-known/agent-card.json"
    assert args.bearer_token == "secret"


def test_cli_requires_command() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args([])
    assert exc_info.value.code == 2


def test_load_settings_reports_missing_upstream_card_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL", raising=False)
    parser = build_parser()
    args = parser.parse_args(["ilink-run"])

    with pytest.raises(SystemExit) as exc_info:
        _load_settings(parser, args)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "missing upstream A2A Agent Card URL" in captured.err
    assert "WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL" in captured.err
    assert "--upstream-a2a-card-url" in captured.err


def test_load_settings_reads_upstream_card_url_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv(
        "WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL",
        "https://agent.example/.well-known/agent-card.json",
    )
    parser = build_parser()
    args = parser.parse_args(["ilink-run"])

    settings = _load_settings(parser, args)

    assert (
        settings.upstream_a2a_card_url_value == "https://agent.example/.well-known/agent-card.json"
    )


def test_load_settings_reads_upstream_card_url_from_persistent_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL", raising=False)
    config_path = tmp_path / ".wechat_to_a2a" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"upstream_a2a_card_url": "https://saved.example/.well-known/agent-card.json"}',
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(["ilink-run"])

    settings = _load_settings(parser, args)

    assert (
        settings.upstream_a2a_card_url_value == "https://saved.example/.well-known/agent-card.json"
    )


def test_load_settings_prefers_env_over_persistent_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv(
        "WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL",
        "https://env.example/.well-known/agent-card.json",
    )
    config_path = tmp_path / ".wechat_to_a2a" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"upstream_a2a_card_url": "https://saved.example/.well-known/agent-card.json"}',
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(["ilink-run"])

    settings = _load_settings(parser, args)

    assert settings.upstream_a2a_card_url_value == "https://env.example/.well-known/agent-card.json"


def test_load_settings_prefers_cli_over_env_and_persistent_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv(
        "WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL",
        "https://env.example/.well-known/agent-card.json",
    )
    config_path = tmp_path / ".wechat_to_a2a" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"upstream_a2a_card_url": "https://saved.example/.well-known/agent-card.json"}',
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(
        [
            "ilink-run",
            "--upstream-a2a-card-url",
            "https://cli.example/.well-known/agent-card.json",
        ]
    )

    settings = _load_settings(parser, args)

    assert settings.upstream_a2a_card_url_value == "https://cli.example/.well-known/agent-card.json"


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
