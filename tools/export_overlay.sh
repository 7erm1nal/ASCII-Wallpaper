#!/usr/bin/env bash
# Выгрузить текущий статичный ASCII-фон в tools/overlay/overlay.txt для ручной правки (см. OVERLAY.md).
# Без --force не перезапишет существующий overlay.txt (чтобы не потерять ваши правки).
set -euo pipefail
cd "$(dirname "$0")"
MASKS="${1:-masks.psd}"; [ $# -gt 0 ] && shift
ARGS=()
[ -e "$MASKS" ] && ARGS+=(--masks "$MASKS")
[ -d masks_extra ] && ARGS+=(--masks masks_extra)
venv/bin/python3 gen_scene.py reference.jpg "${ARGS[@]}" -o /tmp/ascii-street-export.js --geometry geometry.json --cols 320 --export-overlay "$@"
