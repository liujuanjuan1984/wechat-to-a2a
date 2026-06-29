# wechat-to-a2a

`wechat-to-a2a` is a WeChat gateway for upstream A2A-compatible agents.

It keeps WeChat as the user-facing chat surface while your A2A agent remains
the upstream service that provides the actual agent behavior.

## What It Does

- Receives text messages from WeChat.
- Forwards user input to an upstream A2A agent.
- Preserves multi-turn conversation context.
- Starts a fresh conversation after a configurable idle timeout.
- Lets users reset the conversation with `/reset`.
- Supports two gateway modes:
  - `ilink-run` for quick trials through iLink QR login.
  - `serve` for official WeChat public account webhook deployments.

## Installation

Install from PyPI:

```bash
pip install wechat-to-a2a
```

For local development, use `uv`:

```bash
uv sync --all-extras
```

## Quick Start With iLink

Use this mode when you want to try the gateway without a public webhook URL.

```bash
wechat-to-a2a ilink-login
wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json"
wechat-to-a2a ilink-run
```

If the upstream A2A agent requires a bearer token:

```bash
wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json" \
  --bearer-token "optional-upstream-token"
```

## Official WeChat Webhook Mode

Use this mode when you already have an official WeChat public account and a
public HTTPS endpoint.

```bash
export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

wechat-to-a2a serve --host 127.0.0.1 --port 8000
```

Configure the WeChat callback URL as:

```text
https://your-domain.example/wechat
```

## Runtime State

By default, the gateway stores local state under `~/.wechat_to_a2a/`:

- Conversation state: `~/.wechat_to_a2a/conversations.json`
- Upstream A2A configuration: `~/.wechat_to_a2a/config.json`
- iLink login state: `~/.wechat_to_a2a/ilink/`

This storage model is intended for single-node trials and early deployments. It
is not a distributed state backend.

## Configuration

The most commonly used settings are:

- `WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL`
- `WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN`
- `WECHAT_TO_A2A_WECHAT_TOKEN`

When using `ilink-run`, credentials are normally saved by `ilink-login`.

## Development

Use `uv` for dependency management:

```bash
uv sync --all-extras
bash ./scripts/doctor.sh
```

`doctor.sh` runs formatting, linting, type checks, tests, coverage enforcement,
runtime dependency auditing, package builds, and a wheel smoke test.

## Security

Do not include live WeChat tokens, upstream A2A bearer tokens, request payloads,
or user identifiers in public issues.

The gateway should not log WeChat message bodies or upstream bearer tokens.

## License

Apache-2.0
