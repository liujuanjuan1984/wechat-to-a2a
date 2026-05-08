#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=./health_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/health_common.sh"

run_shared_repo_health_prerequisites "doctor"

echo "[doctor] run lint and type checks"
uv run pre-commit run --all-files

echo "[doctor] run tests"
uv run pytest

echo "[doctor] enforce coverage policy"
uv run python ./scripts/check_coverage.py

echo "[doctor] audit runtime dependencies"
runtime_requirements="$(mktemp)"
trap 'rm -f "${runtime_requirements}"' EXIT
uv export --format requirements.txt --no-dev --locked --no-emit-project --output-file "${runtime_requirements}" >/dev/null
uv run pip-audit --requirement "${runtime_requirements}"

echo "[doctor] build package artifacts"
rm -rf build dist
uv build --no-sources

echo "[doctor] smoke test built wheel"
bash ./scripts/smoke_test_built_cli.sh dist/wechat_to_a2a-*.whl
