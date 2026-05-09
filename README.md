# wechat-to-a2a

一个面向任意 A2A 1.0 兼容 Agent 的微信网关。

`wechat-to-a2a` 让你可以继续把微信作为用户入口，同时把消息转发给上游
A2A Agent。它是一个网关，不是把微信本身包装成 A2A 服务。

## 为什么需要它

很多 Agent 系统已经实现了 A2A，但它们的真实用户并不在 A2A 客户端里，而是在微信里。
`wechat-to-a2a` 解决的就是这层连接问题：

- 用户在微信里发消息、收消息
- 网关把文本轮次转发给上游 A2A Agent
- 上游 Agent 继续承担核心智能能力
- 网关负责处理微信侧的接入细节，例如 webhook、轮询、回复格式化和会话连续性

## 产品定位

当前状态：alpha。

如果你需要以下能力，这个项目是合适的：

- 给现有 A2A Agent 增加一个轻量的微信入口
- 在微信公众号 webhook 模式与 iLink 二维码登录模式之间做选择
- 基于上游 A2A `contextId` 和 `taskId` 提供基础的多轮连续对话
- 在不引入数据库的前提下先完成本地持久化

这个项目不打算解决以下问题：

- 把微信暴露成一个 A2A 服务
- 替代你的上游 Agent 运行时
- 提供多租户控制平面或分布式存储方案

## 运行模式

`wechat-to-a2a` 目前支持两种面向操作者的运行模式。

### `ilink-run`

适合想要尽快跑通、接入成本更低的场景。

- 通过腾讯 iLink 二维码流程登录
- 长轮询微信消息
- 通过 iLink `sendmessage` 回消息
- 不需要公网回调地址

### `serve`

适合已经有微信公众号，并且已经具备公网服务入口的场景。

- 暴露一个 FastAPI 应用
- 校验微信回调签名
- 处理微信公众号文本消息 webhook
- 需要一个公网 HTTPS 回调地址

## 核心能力

- 微信公众号 webhook 签名校验
- 类个人微信场景的 iLink 二维码登录与长轮询
- 文本消息转发到上游 A2A Agent
- 流式 A2A 响应消费
- 上游 Bearer Token 鉴权
- 按微信账号 / 用户维度维护会话状态
- 跨轮次复用 A2A `contextId`
- 对 `input-required`、`auth-required`、`working` 等状态复用 A2A `taskId`
- 会话空闲超过 6 小时后自动过期
- 支持本地 `/reset` 命令开启新会话
- 面向微信的回复分片与格式整理
- 基于本地 JSON 文件保存网关配置与会话状态

## 快速开始

### 方式 A：iLink

安装依赖并登录：

```bash
uv sync --all-extras
uv run wechat-to-a2a ilink-login
```

保存上游 A2A Agent Card：

```bash
uv run wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json"
```

如果上游 Agent 需要鉴权：

```bash
uv run wechat-to-a2a config set-upstream \
  --card-url "http://127.0.0.1:8080/.well-known/agent-card.json" \
  --bearer-token "optional-upstream-token"
```

启动网关：

```bash
uv run wechat-to-a2a ilink-run
```

你也可以跳过本地保存的凭据，直接使用环境变量：

```bash
export WECHAT_TO_A2A_ILINK_ACCOUNT_ID="your-ilink-account-id"
export WECHAT_TO_A2A_ILINK_TOKEN="your-ilink-token"
export WECHAT_TO_A2A_ILINK_BASE_URL="https://ilinkai.weixin.qq.com"
uv run wechat-to-a2a ilink-run
```

### 方式 B：微信公众号

```bash
uv sync --all-extras

export WECHAT_TO_A2A_WECHAT_TOKEN="wechat-callback-token"
export WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL="http://127.0.0.1:8080/.well-known/agent-card.json"
export WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN="optional-upstream-token"

uv run wechat-to-a2a serve --host 127.0.0.1 --port 8000
```

然后把微信公众号回调地址配置为：

```text
https://your-domain.example/wechat
```

## 会话行为

网关按“微信接入方式 / 微信账号 / 微信用户”这个组合维度维护会话状态。

- 正常连续对话会复用上游 A2A `contextId`
- 如果上游 Agent 返回 `input-required`、`auth-required` 或 `working` 等续接状态，
  下一轮会继续带上返回的 `taskId`
- 如果一个会话超过 6 小时没有新的交互，下一条入站消息会自动开启新的上游会话
- 如果用户发送 `/reset`，网关会本地清空保存的 `contextId` 和 `taskId`，且不会把该命令透传给上游

## 本地存储

默认情况下，网关会把本地状态保存为 JSON 文件：

- 会话状态：`~/.wechat_to_a2a/conversations.json`
- 保存的上游配置：`~/.wechat_to_a2a/config.json`
- iLink 凭据与同步状态：`~/.wechat_to_a2a/ilink/`

这适合单机部署、试用和评估阶段，不是一个分布式存储方案。

## 配置项

环境变量统一使用 `WECHAT_TO_A2A_` 前缀。上游 A2A Agent Card URL 和 Bearer Token
也可以通过 `wechat-to-a2a config set-upstream` 本地保存。

| 变量 | 是否必需 | 说明 |
| --- | --- | --- |
| `WECHAT_TO_A2A_WECHAT_TOKEN` | 仅微信公众号模式必需 | 微信公众号回调设置中的 token |
| `WECHAT_TO_A2A_UPSTREAM_A2A_CARD_URL` | 是，除非已保存到本地配置 | 上游 A2A 1.0 Agent Card URL |
| `WECHAT_TO_A2A_UPSTREAM_A2A_BEARER_TOKEN` | 否 | 获取 Agent Card 和调用上游 A2A 时使用的 Bearer Token |
| `WECHAT_TO_A2A_UPSTREAM_A2A_TIMEOUT_SECONDS` | 否 | 获取 Agent Card 与非流式上游请求的超时时间，默认 `300` |
| `WECHAT_TO_A2A_UPSTREAM_A2A_STREAM_IDLE_TIMEOUT_SECONDS` | 否 | 等待上游流式输出活动的空闲超时时间，默认 `60`；设为 `0` 表示关闭 |
| `WECHAT_TO_A2A_CONVERSATION_STATE_PATH` | 否 | 本地会话状态 JSON 文件路径 |
| `WECHAT_TO_A2A_WECHAT_REPLY_MAX_CHARS` | 否 | 每个微信回复分片允许的最大字符数，默认 `2000` |
| `WECHAT_TO_A2A_WECHAT_SPLIT_MULTILINE_MESSAGES` | 否 | 是否在拼接前把较短的多行回复拆成多个分片 |
| `WECHAT_TO_A2A_ILINK_ACCOUNT_ID` | 否 | `ilink-run` 使用的 iLink 账号 ID；有已保存登录态时可自动推断 |
| `WECHAT_TO_A2A_ILINK_TOKEN` | 否 | `ilink-run` 使用的 iLink bot token；有已保存登录态时可自动加载 |
| `WECHAT_TO_A2A_ILINK_BASE_URL` | 否 | iLink API base URL，默认 `https://ilinkai.weixin.qq.com` |

## 开发校验

本地开发时建议执行：

```bash
bash ./scripts/doctor.sh
bash ./scripts/dependency_health.sh
```

## License

Apache-2.0
