#!/usr/bin/env bash
# iglegais one-liner:
#   curl -fsSL https://raw.githubusercontent.com/Cintu07/iglegais/main/install.sh | bash
set -euo pipefail

echo ""
echo "  iglegais installer"
echo ""

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "  error: python 3.10+ required" >&2
  exit 1
fi

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

echo "  · pip install iglegais"
"$PY" -m pip install -U iglegais

echo "  · running iglegais-setup"
# pass through flags: install.sh -y --key csk-...
exec "$PY" -m iglegais.setup_cmd "$@"
