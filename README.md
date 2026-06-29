# wechat-to-a2a

Languages: [English](#english) | [简体中文](#简体中文)

## English

`wechat-to-a2a` is a WeChat gateway for upstream A2A-compatible agents.

It keeps WeChat as the user-facing chat surface while your A2A agent remains
the upstream service that provides the actual agent behavior.

## What It Does

- Receives text messages from WeChat.
- Forwards user input to an upstream A2A agent.
- Preserves multi-turn conversation context.
- Starts a fresh conversation after a configurable idle timeout.
- Lets users reset the conversation with `/reset`.
- Supports two WeChat entry modes:
  - `ilink-run` for iLink QR login without a public webhook endpoint.
  - `serve` for official WeChat public account callback handling at `/wechat`.

## Installation

Install from PyPI:

```bash
pip install wechat-to-a2a
```

For local development, use `uv`:

```bash
uv sync --all-extras
```

## iLink Mode

Use this mode when you want WeChat access through iLink QR login without running
a public WeChat webhook endpoint.

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

## Official WeChat Public Account Mode

Use this mode when you already have an official WeChat public account and a
public HTTPS endpoint.

This mode currently handles plaintext XML callbacks with token signature
verification and text messages.

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

## 简体中文

`wechat-to-a2a` 是一个把微信接到上游 A2A 兼容 Agent 的网关。

它让微信继续作为面向用户的聊天入口，同时让你的 A2A Agent 继续作为提供
Agent 能力的上游服务。

## 它能做什么

- 接收微信文本消息。
- 把用户输入转发给上游 A2A Agent。
- 保持多轮对话上下文。
- 会话空闲超时后自动开启新会话。
- 用户可以发送 `/reset` 手动重置会话。
- 支持两种微信入口模式：
  - `ilink-run`：通过 iLink 扫码登录，不需要公网 webhook 入口。
  - `serve`：提供微信公众号 `/wechat` 回调处理入口。

## 安装

从 PyPI 安装：

```bash
pip install wechat-to-a2a
```

本地开发使用 `uv`：

```bash
uv sync --all-extras
```

## iLink 模式

如果你希望通过 iLink 扫码登录接入微信，并且不想运行公网微信公众号 webhook
入口，可以使用这个模式。

```bash
wechat-to-a2a ilink-login
wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json"
wechat-to-a2a ilink-run
```

如果上游 A2A Agent 需要 bearer token：

```bash
wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json" \
  --bearer-token "optional-upstream-token"
```

## 微信公众号模式

如果你已经有微信公众号和公网 HTTPS 入口，可以使用这个模式。

当前该模式处理明文 XML 回调，使用 token signature 校验，并支持文本消息。

```bash
export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

wechat-to-a2a serve --host 127.0.0.1 --port 8000
```

然后把微信公众号回调地址配置为：

```text
https://your-domain.example/wechat
```

## 运行状态

默认情况下，网关会把本地状态保存在 `~/.wechat_to_a2a/` 下：

- 会话状态：`~/.wechat_to_a2a/conversations.json`
- 上游 A2A 配置：`~/.wechat_to_a2a/config.json`
- iLink 登录状态：`~/.wechat_to_a2a/ilink/`

这个存储模型适合单机试用和早期部署，不是分布式状态后端。

## 配置

最常用的配置项是：

- `WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL`
- `WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN`
- `WECHAT_TO_A2A_WECHAT_TOKEN`

使用 `ilink-run` 时，凭据通常会由 `ilink-login` 自动保存。

## 开发

使用 `uv` 管理依赖：

```bash
uv sync --all-extras
bash ./scripts/doctor.sh
```

`doctor.sh` 会运行格式化、lint、类型检查、测试、覆盖率检查、运行时依赖漏洞审计、
包构建和 wheel 冒烟测试。

## 安全

请不要在公开 issue 中包含真实微信 token、上游 A2A bearer token、请求 payload 或用户标识符。

网关不应记录微信消息正文或上游 bearer token。

## 许可证

Apache-2.0
