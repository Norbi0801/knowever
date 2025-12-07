#!/usr/bin/env bash
# Simple startup script to fetch RSS entries and send the daily digest.
# Put this in a systemd unit / scheduled task to run at boot.

set -euo pipefail

# Resolve project root (directory of this script)
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# Ensure Node/NVM bins are on PATH (non-interactive shells don't load nvm)
if [[ -d "${HOME}/.nvm" ]]; then
  latest_node_bin="$(ls -1 "${HOME}/.nvm/versions/node" 2>/dev/null | sort -V | tail -n1)"
  if [[ -n "$latest_node_bin" && -d "${HOME}/.nvm/versions/node/${latest_node_bin}/bin" ]]; then
    export PATH="${HOME}/.nvm/versions/node/${latest_node_bin}/bin:${PATH}"
  fi
fi

LOG_DIR="${BASE_DIR}/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
LOG_FILE="${LOG_DIR}/run_${TIMESTAMP}.log"

# Keep caches/state inside the project (sandbox-friendly)
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${BASE_DIR}/.cache}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-${BASE_DIR}/.local/state}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME}/uv}"
export PYTHONPATH="${BASE_DIR}/src:${PYTHONPATH:-}"
mkdir -p "$XDG_CACHE_HOME" "$XDG_STATE_HOME" "$UV_CACHE_DIR"

# Load environment (SMTP, limits, flags)
if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

# Basic dependency check
if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; install from https://astral.sh/uv" | tee -a "$LOG_FILE"
  exit 1
fi

{
  echo "[${TIMESTAMP}] starting pipeline (uv run -m knowever.cli run)"
  uv run -m knowever.cli run
  echo "[${TIMESTAMP}] finished."
} | tee -a "$LOG_FILE"
