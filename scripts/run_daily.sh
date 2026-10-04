#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
elif [ -f venv/bin/activate ]; then
  . venv/bin/activate
fi

python -m sepa_bot.main --once
