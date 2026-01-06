#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if command -v uv >/dev/null 2>&1; then
  exec uv tool run --from . gitlab-autobot-mcp
fi

if command -v python >/dev/null 2>&1; then
  if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    exec gitlab-autobot-mcp
  fi
fi

cat <<'EOF'
Unable to start gitlab-autobot-mcp.

Install uv and run:
  uv tool run --from . gitlab-autobot-mcp

Or create a virtual environment:
  python -m venv .venv
  source .venv/bin/activate
  pip install -e .
  gitlab-autobot-mcp
EOF
exit 1
