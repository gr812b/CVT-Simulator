#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="${API:-http://localhost:8000/api/v1}"
python "$SCRIPT_DIR/cvt_black_box_api_e2e.py" --api "$API" "$@"
