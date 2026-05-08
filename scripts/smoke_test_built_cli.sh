#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -gt 1 ]]; then
  echo "Expected at most one built artifact path argument" >&2
  exit 1
fi

artifact_path="${1:-}"
if [[ -z "${artifact_path}" ]]; then
  shopt -s nullglob
  wheel_paths=(dist/wechat_to_a2a-*.whl)
  shopt -u nullglob
  if [[ "${#wheel_paths[@]}" -ne 1 ]]; then
    echo "Expected exactly one built wheel in dist/" >&2
    exit 1
  fi
  artifact_path="${wheel_paths[0]}"
fi

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

UV_TOOL_DIR="${tmpdir}/tools" \
UV_TOOL_BIN_DIR="${tmpdir}/bin" \
uv tool install "${artifact_path}" --python python3

"${tmpdir}/bin/wechat-to-a2a" --help >/dev/null
