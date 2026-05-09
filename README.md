# wechat-to-a2a

A WeChat gateway for chatting with any A2A 1.0-compatible agent.

`wechat-to-a2a` lets you keep WeChat as the user-facing channel while routing
messages to an upstream A2A agent. It is a gateway, not a WeChat-as-A2A
service.

## Why This Exists

Many agent deployments already speak A2A, but their users live in WeChat.
`wechat-to-a2a` bridges that gap:

- Users send and receive messages in WeChat
- The gateway forwards text turns to an upstream A2A agent
- The upstream agent remains the system of intelligence
- The gateway manages WeChat-specific concerns such as webhook handling,
  polling, reply formatting, and conversation continuity

## Product Shape

Current status: alpha.

This project is useful when you want:

- A lightweight WeChat entrypoint for an existing A2A agent
- A choice between WeChat Official Account webhook mode and iLink QR-login mode
- Basic multi-turn continuity using upstream A2A `contextId` and `taskId`
- Simple local persistence without introducing a database

This project is not trying to:

- Turn WeChat into an A2A service
- Replace your upstream agent runtime
- Provide a multi-tenant control plane or distributed storage layer

## Choose a Mode

`wechat-to-a2a` supports two operator-facing modes.

### `ilink-run`

Best when you want the fastest path to a working gateway.

- Login through Tencent iLink QR flow
- Long-poll WeChat messages
- Reply through iLink `sendmessage`
- No public callback URL required

### `serve`

Best when you already run a public service for a WeChat Official Account.

- Exposes a FastAPI app
- Verifies WeChat callback signatures
- Handles Official Account text message webhooks
- Requires a public HTTPS callback URL

## Core Capabilities

- WeChat Official Account webhook verification
- WeChat personal-account style iLink QR login and long polling
- Text-message forwarding to upstream A2A agents
- Streaming A2A response consumption
- Upstream bearer-token authentication
- Per-WeChat-account/user conversation state
- A2A `contextId` reuse across turns
- A2A `taskId` continuation for `input-required`, `auth-required`, and `working`
  tasks
- Idle conversation expiry after six hours without interaction
- Local `/reset` command to start a fresh upstream conversation
- WeChat-oriented reply chunking and formatting
- Local JSON persistence for gateway configuration and conversation state

## Quick Start

### Option A: iLink

Install dependencies and login:

```bash
uv sync --all-extras
uv run wechat-to-a2a ilink-login
```

Save the upstream A2A Agent Card:

```bash
uv run wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json"
```

If the upstream agent requires auth:

```bash
uv run wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json" \
  --bearer-token "optional-upstream-token"
```

Run the gateway:

```bash
uv run wechat-to-a2a ilink-run
```

You can also bypass saved credentials:

```bash
export WECHAT_TO_A2A_ILINK_ACCOUNT_ID="your-ilink-account-id"
export WECHAT_TO_A2A_ILINK_TOKEN="your-ilink-token"
export WECHAT_TO_A2A_ILINK_BASE_URL="https://ilinkai.weixin.qq.com"
uv run wechat-to-a2a ilink-run
```

### Option B: Official Account

```bash
uv sync --all-extras

export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

uv run wechat-to-a2a serve --host 127.0.0.1 --port 8000
```

Then configure your WeChat Official Account callback URL:

```text
https://your-domain.example/wechat
```

## Conversation Behavior

The gateway keeps conversation state per WeChat gateway/account/user
combination.

- The upstream A2A `contextId` is reused across normal follow-up turns
- When the upstream agent returns a continuation state such as
  `input-required`, `auth-required`, or `working`, the returned `taskId` is
  reused on the next turn
- If a conversation stays idle for more than six hours, the next inbound
  message starts a fresh upstream conversation
- Sending `/reset` clears the stored upstream `contextId` and `taskId` without
  forwarding the command upstream

## Local Storage

By default, the gateway stores local state in JSON files:

- Conversation state: `~/.wechat_to_a2a/conversations.json`
- Saved upstream configuration: `~/.wechat_to_a2a/config.json`
- iLink credentials and sync state: `~/.wechat_to_a2a/ilink/`

This is suitable for single-host usage and evaluation. It is not a distributed
storage design.

## Configuration

Environment variables use the `WECHAT_TO_A2A_` prefix. The upstream A2A Agent
Card URL and bearer token can also be saved with
`wechat-to-a2a config set-upstream`.

| Variable | Required | Description |
| --- | --- | --- |
| `WECHAT_TO_A2A_WECHAT_TOKEN` | Official mode only | Token configured in WeChat Official Account callback settings |
| `WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL` | Yes, unless saved in config | Upstream A2A 1.0 Agent Card URL |
| `WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN` | No | Bearer token used for Agent Card fetches and upstream A2A calls |
| `WECHAT_TO_A2A_UPSTREAM_A2A_TIMEOUT_SECONDS` | No | Timeout for Agent Card fetches and non-streaming upstream turns, default `300` |
| `WECHAT_TO_A2A_UPSTREAM_A2A_STREAM_IDLE_TIMEOUT_SECONDS` | No | Idle timeout while waiting for upstream stream activity, default `60`; set `0` to disable |
| `WECHAT_TO_A2A_CONVERSATION_STATE_PATH` | No | Path to the local conversation-state JSON file |
| `WECHAT_TO_A2A_WECHAT_REPLY_MAX_CHARS` | No | Maximum text characters per WeChat reply chunk, default `2000` |
| `WECHAT_TO_A2A_WECHAT_SPLIT_MULTILINE_MESSAGES` | No | Split short multiline replies into separate chunks before joining |
| `WECHAT_TO_A2A_ILINK_ACCOUNT_ID` | No | iLink account ID for `ilink-run`; inferred from saved login when possible |
| `WECHAT_TO_A2A_ILINK_TOKEN` | No | iLink bot token for `ilink-run`; loaded from saved login when possible |
| `WECHAT_TO_A2A_ILINK_BASE_URL` | No | iLink API base URL, default `https://ilinkai.weixin.qq.com` |

## Development

For local validation:

```bash
bash ./scripts/doctor.sh
bash ./scripts/dependency_health.sh
```

## License

Apache-2.0
