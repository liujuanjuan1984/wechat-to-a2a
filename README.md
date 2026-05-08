# wechat-to-a2a

A WeChat gateway for chatting with any A2A 1.0-compatible agent.

This project is intentionally a gateway, not a WeChat-as-A2A service. It accepts
WeChat messages, forwards user text to an upstream A2A agent with JSON-RPC
`SendMessage`, and returns the agent reply to WeChat.

## Status

Early gateway. The current implementation supports:

- WeChat Official Account webhook signature verification
- WeChat personal-account style iLink QR login and long polling
- WeChat text-message XML parsing and text replies
- Per-WeChat-account/user A2A conversation state
- A2A `contextId` reuse across WeChat messages
- A2A `taskId` continuation for `input-required`, `auth-required`, and `working` tasks
- Streaming A2A consumption with heartbeat-aware waiting
- Optional JSON conversation-state persistence
- WeChat-oriented text formatting and reply chunking
- Bearer-token authentication for upstream A2A agents
- FastAPI app and `wechat-to-a2a serve` CLI

## How It Works

`wechat-to-a2a` can run in two modes:

- `ilink-run`: preferred low-friction mode. It logs into WeChat via Tencent
  iLink QR credentials, long-polls `getupdates`, and replies with
  `sendmessage`.
- `serve`: WeChat Official Account webhook mode for deployments that already
  have a public HTTPS callback URL.

Both modes fetch the configured upstream A2A 1.0 Agent Card, let `a2a-sdk`
resolve the JSON-RPC endpoint from the card's advertised interfaces, and
forward each inbound text message with `SendMessage`. When the upstream card
advertises streaming, the gateway consumes streaming A2A events and aggregates
the final text before replying to WeChat. The gateway keys conversation state by
WeChat gateway/account/user, then stores the upstream A2A `contextId` so later
WeChat messages continue the same A2A conversation.

When an A2A service returns a non-terminal task state such as `input-required`,
the gateway also stores the returned `taskId` and sends the next WeChat message
back with both `contextId` and `taskId`. Once the task completes, the `taskId` is
cleared while the `contextId` remains available for future turns.

The gateway does not expose WeChat as an A2A service. It is a WeChat entrypoint
for any A2A 1.0-compatible upstream service.

## iLink Quick Start

First login with QR code:

```bash
uv sync --all-extras
uv run wechat-to-a2a ilink-login
```

The login stores iLink credentials under `~/.wechat_to_a2a/ilink` by default.
Then run the gateway against any upstream A2A Agent Card:

```bash
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

uv run wechat-to-a2a ilink-run
```

You can also bypass saved credentials:

```bash
export WECHAT_TO_A2A_ILINK_ACCOUNT_ID="your-ilink-account-id"
export WECHAT_TO_A2A_ILINK_TOKEN="your-ilink-token"
export WECHAT_TO_A2A_ILINK_BASE_URL="https://ilinkai.weixin.qq.com"
uv run wechat-to-a2a ilink-run
```

Conversation state is created automatically at:

```text
~/.wechat_to_a2a/conversations.json
```

## Official Account Quick Start

```bash
uv sync --all-extras

export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

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
| `WECHAT_TO_A2A_WECHAT_TOKEN` | Official mode only | Token configured in WeChat Official Account callback settings |
| `WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL` | Yes | Upstream A2A 1.0 Agent Card URL; the SDK resolves the JSON-RPC endpoint from the card's advertised interfaces |
| `WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN` | No | Bearer token sent when fetching the Agent Card and calling the upstream A2A endpoint |
| `WECHAT_TO_A2A_UPSTREAM_A2A_TIMEOUT_SECONDS` | No | Timeout for Agent Card fetches and non-streaming upstream A2A turns, default `300`; streaming turns are governed by stream idle timeout instead |
| `WECHAT_TO_A2A_UPSTREAM_A2A_STREAMING_ENABLED` | No | Whether to request upstream A2A streaming when the Agent Card supports it, default `true` |
| `WECHAT_TO_A2A_UPSTREAM_A2A_STREAM_IDLE_TIMEOUT_SECONDS` | No | Idle timeout while waiting for upstream stream activity, default `60`; set `0` to disable |
| `WECHAT_TO_A2A_UPSTREAM_A2A_STREAM_HEARTBEAT_INTERVAL_SECONDS` | No | Local heartbeat interval while waiting on upstream stream events, default `15`; set `0` to disable |
| `WECHAT_TO_A2A_CONVERSATION_STATE_PATH` | No | JSON file used to persist WeChat-to-A2A conversation state, default `~/.wechat_to_a2a/conversations.json` |
| `WECHAT_TO_A2A_WECHAT_REPLY_MAX_CHARS` | No | Maximum text characters per WeChat reply chunk, default `2000` |
| `WECHAT_TO_A2A_WECHAT_SPLIT_MULTILINE_MESSAGES` | No | Split short multiline replies into separate chunks before joining, default `false` |
| `WECHAT_TO_A2A_ILINK_ACCOUNT_ID` | No | iLink account ID for `ilink-run`; inferred from saved login when possible |
| `WECHAT_TO_A2A_ILINK_TOKEN` | No | iLink bot token for `ilink-run`; loaded from saved login when possible |
| `WECHAT_TO_A2A_ILINK_BASE_URL` | No | iLink API base URL, default `https://ilinkai.weixin.qq.com` |

## License

Apache-2.0
