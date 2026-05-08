# wechat-to-a2a

A WeChat gateway for chatting with any A2A-compatible agent.

This project is intentionally a gateway, not a WeChat-as-A2A service. It accepts
WeChat Official Account webhook messages, forwards user text to an upstream A2A
agent with JSON-RPC `SendMessage`, and returns the agent reply to WeChat.

## Status

Early scaffold. The current implementation supports:

- WeChat Official Account webhook signature verification
- WeChat text-message XML parsing and text replies
- Per-WeChat-user A2A `contextId` mapping
- Bearer-token authentication for upstream A2A agents
- FastAPI app and `wechat-to-a2a serve` CLI

## Quick Start

```bash
uv sync --all-extras

export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_A2A_URL="http://127.0.0.1:8080/"
export WECHAT_TO_A2A_A2A_BEARER_TOKEN="optional-upstream-token"

uv run wechat-to-a2a serve --host 127.0.0.1 --port 8000
```

Configure your WeChat Official Account callback URL to:

```text
https://your-domain.example/wechat
```

## Local Checks

```bash
bash ./scripts/doctor.sh
bash ./scripts/dependency_health.sh
```

## Configuration

Environment variables use the `WECHAT_TO_A2A_` prefix.

| Variable | Required | Description |
| --- | --- | --- |
| `WECHAT_TO_A2A_WECHAT_TOKEN` | Yes | Token configured in WeChat Official Account callback settings |
| `WECHAT_TO_A2A_A2A_URL` | Yes | Upstream A2A JSON-RPC endpoint URL |
| `WECHAT_TO_A2A_A2A_BEARER_TOKEN` | No | Bearer token sent to the upstream A2A agent |
| `WECHAT_TO_A2A_A2A_TIMEOUT_SECONDS` | No | A2A request timeout, default `30` |

## License

Apache-2.0
