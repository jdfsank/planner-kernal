#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' '{"status":"BLOCKED","exit_code":2,"error":"uv is required"}'
  exit 2
fi
unset VIRTUAL_ENV UV_PROJECT UV_WORKING_DIRECTORY UV_PYTHON UV_PYTHON_ENVIRONMENT
export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
exec uv sync --project "$ROOT" --python "$(cat "$ROOT/.python-version")" --locked "$@"
