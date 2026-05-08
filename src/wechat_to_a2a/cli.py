from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

import uvicorn

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
from .settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wechat-to-a2a")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the WeChat gateway HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--log-level", default="info")

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    if args.command == "serve":
        settings = Settings()  # type: ignore[call-arg]
        app = create_app(settings)
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
        return 0

    if args.command == "ilink-login":
        state_store = ILinkStateStore(args.state_dir)
        credentials = asyncio.run(
            run_qr_login(
                state_store=state_store,
                bot_type=args.bot_type,
                timeout_seconds=args.timeout,
            )
        )
        return 0 if credentials is not None else 1

    if args.command == "ilink-run":
        settings = Settings()  # type: ignore[call-arg]
        state_store = ILinkStateStore(args.state_dir)
        credentials = _resolve_ilink_credentials(
            state_store=state_store,
            account_id=args.account_id,
            token=args.token,
            base_url=args.base_url,
        )
        a2a_client = A2AClient(
            agent_card_url=settings.upstream_a2a_card_endpoint,
            bearer_token=settings.upstream_a2a_bearer_token,
            timeout_seconds=settings.upstream_a2a_timeout_seconds,
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
        asyncio.run(runner.run_forever())
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


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
        account_id = _single_saved_account_id(state_store)
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


def _single_saved_account_id(state_store: ILinkStateStore) -> str | None:
    return state_store.single_saved_account_id()


if __name__ == "__main__":
    raise SystemExit(main())
