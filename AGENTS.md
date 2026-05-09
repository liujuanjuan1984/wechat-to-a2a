# Repository Instructions

This repository implements a WeChat gateway that talks to upstream A2A-compatible
agents. Keep the direction clear in naming and docs: WeChat is the user-facing
gateway, and A2A agents are upstream services.

## Development

- Use `uv` for dependency management.
- Develop changes on topic branches; keep `main` reserved for reviewed, integrated history.
- Use Conventional Commit messages such as `feat: add wechat webhook` or `fix: handle a2a errors`.
- Run `bash ./scripts/doctor.sh` before release-oriented changes.
- Keep protocol parsing small and well-tested.
- Do not log WeChat message bodies or upstream bearer tokens.
