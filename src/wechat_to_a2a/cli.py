from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import uvicorn
from pydantic import ValidationError

from .a2a_client import A2AClient
from .app import create_app
from .conversation import ConversationStore
from .gateway import WeChatA2AGateway
from .ilink import (
    ILinkClient,
    ILinkCredentials,
    ILinkGatewayRunner,
    ILinkStateStore,
    default_ilink_state_dir,
    run_qr_login,
)
from .settings import (
    UPSTREAM_A2A_BEARER_TOKEN_ENV,
    UPSTREAM_A2A_CARD_URL_ENV,
    Settings,
    default_config_path,
    load_persistent_config,
    save_upstream_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wechat-to-a2a")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the WeChat gateway HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--log-level", default="warning")
    _add_upstream_a2a_args(serve)

    ilink_login = subparsers.add_parser("ilink-login", help="Login to WeChat via iLink QR")
    ilink_login.add_argument("--state-dir", type=Path, default=default_ilink_state_dir())
    ilink_login.add_argument("--bot-type", default="3")
    ilink_login.add_argument("--timeout", type=int, default=480)

    ilink_run = subparsers.add_parser("ilink-run", help="Run the iLink WeChat gateway")
    ilink_run.add_argument("--account-id")
    ilink_run.add_argument("--token")
    ilink_run.add_argument("--base-url")
    ilink_run.add_argument("--state-dir", type=Path, default=default_ilink_state_dir())
    ilink_run.add_argument("--poll-interval", type=float, default=1.0)
    ilink_run.add_argument("--send-chunk-delay", type=float, default=1.5)
    _add_upstream_a2a_args(ilink_run)

    config = subparsers.add_parser("config", help="Manage local configuration")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    set_upstream = config_subparsers.add_parser(
        "set-upstream",
        help="Persist upstream A2A Agent Card settings locally",
    )
    set_upstream.add_argument("--card-url", required=True)
    set_upstream.add_argument("--bearer-token")
    set_upstream.add_argument("--clear-bearer-token", action="store_true")
    show_config = config_subparsers.add_parser("show", help="Show local configuration")
    show_config.add_argument("--show-token", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    if args.command == "serve":
        settings = _load_settings(parser, args)
        app = create_app(settings)
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
        return 0

    if args.command == "ilink-login":
        state_store = ILinkStateStore(args.state_dir)
        login_result = asyncio.run(
            run_qr_login(
                state_store=state_store,
                bot_type=args.bot_type,
                timeout_seconds=args.timeout,
            )
        )
        return 0 if login_result is not None else 1

    if args.command == "ilink-run":
        settings = _load_settings(parser, args)
        state_store = ILinkStateStore(args.state_dir)
        try:
            credentials = _resolve_ilink_credentials(
                state_store=state_store,
                account_id=args.account_id,
                token=args.token,
                base_url=args.base_url,
            )
        except RuntimeError as exc:
            parser.exit(2, f"{parser.prog}: {exc}\n")
        a2a_client = A2AClient(
            agent_card_url=str(settings.upstream_a2a_card_url),
            bearer_token=settings.upstream_a2a_bearer_token,
            timeout_seconds=settings.upstream_a2a_timeout_seconds,
            stream_idle_timeout_seconds=settings.upstream_a2a_stream_idle_timeout_seconds,
        )
        gateway = WeChatA2AGateway(
            a2a_client=a2a_client,
            conversation_store=ConversationStore(settings.conversation_state_path),
            reply_max_chars=settings.wechat_reply_max_chars,
            split_multiline_messages=settings.wechat_split_multiline_messages,
        )
        ilink_client = ILinkClient(
            base_url=credentials.base_url,
            token=credentials.token,
        )
        runner = ILinkGatewayRunner(
            account_id=credentials.account_id,
            ilink_client=ilink_client,
            gateway=gateway,
            state_store=state_store,
            poll_interval_seconds=args.poll_interval,
            send_chunk_delay_seconds=args.send_chunk_delay,
        )
        logging.info("Starting iLink gateway for account_id=%s", credentials.account_id)
        return _run_until_interrupted(
            _run_ilink_gateway(
                runner=runner,
                a2a_client=a2a_client,
                ilink_client=ilink_client,
            )
        )

    if args.command == "config":
        if args.config_command == "set-upstream":
            if args.bearer_token and args.clear_bearer_token:
                parser.error("--bearer-token and --clear-bearer-token cannot be used together")
            try:
                config_path = save_upstream_config(
                    card_url=args.card_url,
                    bearer_token=args.bearer_token,
                    clear_bearer_token=args.clear_bearer_token,
                )
            except ValidationError as exc:
                parser.exit(2, _format_settings_error(parser.prog, exc))
            except RuntimeError as exc:
                parser.exit(2, f"{parser.prog}: configuration error: {exc}\n")
            print(f"Saved upstream A2A configuration to {config_path}")
            return 0
        if args.config_command == "show":
            try:
                _print_config(show_token=args.show_token)
            except RuntimeError as exc:
                parser.exit(2, f"{parser.prog}: configuration error: {exc}\n")
            return 0
        parser.error(f"unknown config command: {args.config_command}")

    parser.error(f"unknown command: {args.command}")
    return 2


def _add_upstream_a2a_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--upstream-a2a-card-url",
        help=(
            "Upstream A2A Agent Card URL. Can also be set with WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL."
        ),
    )
    parser.add_argument(
        "--upstream-a2a-bearer-token",
        help=(
            "Optional bearer token for the upstream A2A Agent Card and endpoint. Can also "
            "be set with WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN."
        ),
    )


def _load_settings(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Settings:
    try:
        overrides = _persistent_settings_overrides()
        if args.upstream_a2a_card_url:
            overrides["upstream_a2a_card_url"] = args.upstream_a2a_card_url
        if args.upstream_a2a_bearer_token:
            overrides["upstream_a2a_bearer_token"] = args.upstream_a2a_bearer_token
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        parser.exit(2, _format_settings_error(parser.prog, exc))
    except RuntimeError as exc:
        parser.exit(2, f"{parser.prog}: configuration error: {exc}\n")


def _persistent_settings_overrides() -> dict[str, str]:
    values = load_persistent_config()
    if UPSTREAM_A2A_CARD_URL_ENV in os.environ:
        values.pop("upstream_a2a_card_url", None)
    if UPSTREAM_A2A_BEARER_TOKEN_ENV in os.environ:
        values.pop("upstream_a2a_bearer_token", None)
    return values


def _print_config(*, show_token: bool) -> None:
    config_path = default_config_path()
    values = load_persistent_config(config_path)
    print(f"Config file: {config_path}")
    print(f"upstream_a2a_card_url: {values.get('upstream_a2a_card_url', '<unset>')}")
    token = values.get("upstream_a2a_bearer_token")
    if show_token:
        print(f"upstream_a2a_bearer_token: {token or '<unset>'}")
    else:
        print(f"upstream_a2a_bearer_token: {'<set>' if token else '<unset>'}")


def _format_settings_error(prog: str, exc: ValidationError) -> str:
    for error in exc.errors():
        if tuple(error["loc"]) == ("upstream_a2a_card_url",) and error["type"] == "missing":
            return (
                f"{prog}: configuration error: missing upstream A2A Agent Card URL.\n"
                "Set WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL or pass "
                "--upstream-a2a-card-url.\n"
                "Example:\n"
                "  export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="
                '"https://example.com/.well-known/agent-card.json"\n'
            )
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return f"{prog}: configuration error: {details}\n"


def _resolve_ilink_credentials(
    *,
    state_store: ILinkStateStore,
    account_id: str | None,
    token: str | None,
    base_url: str | None,
) -> ILinkCredentials:
    account_id = account_id or os.getenv("WECHAT_TO_A2A_ILINK_ACCOUNT_ID")
    token = token or os.getenv("WECHAT_TO_A2A_ILINK_TOKEN")
    base_url = base_url or os.getenv("WECHAT_TO_A2A_ILINK_BASE_URL")

    if not account_id:
        account_id = state_store.single_saved_account_id() or state_store.latest_saved_account_id()
    if not account_id:
        raise RuntimeError("iLink account id is required; run `wechat-to-a2a ilink-login` first")

    saved = state_store.load_credentials(account_id)
    token = token or (saved.token if saved else None)
    base_url = base_url or (saved.base_url if saved else None)
    user_id = saved.user_id if saved else ""
    if not token:
        raise RuntimeError("iLink token is required; run `wechat-to-a2a ilink-login` first")
    return ILinkCredentials(
        account_id=account_id,
        token=token,
        base_url=base_url or "https://ilinkai.weixin.qq.com",
        user_id=user_id,
    )


def _run_until_interrupted(coro: Coroutine[Any, Any, Any]) -> int:
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        logging.info("Shutdown requested; exiting.")
        return 130
    return 0


async def _run_ilink_gateway(
    *,
    runner: ILinkGatewayRunner,
    a2a_client: A2AClient,
    ilink_client: ILinkClient,
) -> None:
    try:
        await runner.run_forever()
    finally:
        await a2a_client.aclose()
        await ilink_client.aclose()


if __name__ == "__main__":
    raise SystemExit(main())
