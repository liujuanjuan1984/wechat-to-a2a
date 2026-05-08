from __future__ import annotations

import argparse
import logging

import uvicorn

from .app import create_app
from .settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wechat-to-a2a")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the WeChat gateway HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--log-level", default="info")
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

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
