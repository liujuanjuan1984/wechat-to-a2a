# Contributing

## Local Setup

```bash
uv sync --all-extras
uv run pre-commit install
bash ./scripts/doctor.sh
```

## Pull Requests

- Include tests for behavior changes.
- Keep gateway responsibilities separate from upstream agent behavior.
- Document new configuration keys in `README.md`.
