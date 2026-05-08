from __future__ import annotations

import pytest

from wechat_to_a2a.cli import build_parser


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
