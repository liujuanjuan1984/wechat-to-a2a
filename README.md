# wechat-to-a2a

一个把微信接到 A2A Agent 上的网关。

你可以把它理解成：

- 用户继续在微信里聊天
- 你的 Agent 继续提供能力
- `wechat-to-a2a` 负责把两边连起来

它适合这样的场景：

- 你已经有一个支持 A2A 协议、并且能正常工作的 Agent
- 你希望用户直接在微信里使用它
- 你不想先做一套复杂的平台或后台系统

## 它能帮你做到什么

- 让微信成为 Agent 的聊天入口
- 保持多轮对话连续
- 会话空闲太久后自动重新开始
- 用户可以发送 `/reset` 手动开启新会话
- 支持两种接入方式：
  - `ilink-run`：更适合快速试用
  - `serve`：更适合微信公众号正式接入

## 先选一种接入方式

### 方式 A：`ilink-run`

如果你只是想尽快跑起来，优先用这个。

特点：

- 通过 iLink 二维码登录
- 不需要公网回调地址
- 更适合试用、验证和早期接入

启动步骤：

```bash
uv sync --all-extras
uv run wechat-to-a2a ilink-login
uv run wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json"
uv run wechat-to-a2a ilink-run
```

如果你的上游 Agent 需要 token：

```bash
uv run wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json" \
  --bearer-token "optional-upstream-token"
```

### 方式 B：`serve`

如果你已经有微信公众号和公网服务入口，用这个。

启动步骤：

```bash
uv sync --all-extras

export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

uv run wechat-to-a2a serve --host 127.0.0.1 --port 8000
```

然后把微信公众号回调地址配置到：

```text
https://your-domain.example/wechat
```

## 使用时会发生什么

- 用户在微信里发来的文本消息会被转发给上游 Agent
- 正常连续对话会尽量接着上一次上下文继续
- 如果一个会话超过 6 小时没有互动，下一条消息会自动开始新会话
- 如果用户发送 `/reset`，会立即丢弃旧会话，下一轮从头开始

## 本地会保存什么

默认会在本机保存一些简单状态，方便继续使用：

- 会话状态：`~/.wechat_to_a2a/conversations.json`
- 上游配置：`~/.wechat_to_a2a/config.json`
- iLink 登录态：`~/.wechat_to_a2a/ilink/`

这更适合单机使用、试用和早期部署，不是分布式方案。

## 你真正需要关心的配置

大多数情况下，只要关心这几个：

- `WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL`
- `WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN`
- `WECHAT_TO_A2A_WECHAT_TOKEN`（仅微信公众号模式）

如果你使用 `ilink-run`，登录后通常不需要手动再填 iLink 凭据。

## 开发与校验

如果你是在开发或改代码：

```bash
bash ./scripts/doctor.sh
```

## License

Apache-2.0
