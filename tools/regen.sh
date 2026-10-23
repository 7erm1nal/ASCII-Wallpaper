#!/usr/bin/env bash
# Пересобрать сцену из референса, масок и текстовой накладки.
#   ./tools/regen.sh                   # tools/masks.psd (+ tools/masks_extra/*.png), накладка tools/overlay/ если есть
#   ./tools/regen.sh path/to/my.psd    # свой PSD
# Любые дополнительные ключи gen_scene.py передаются после PSD, например:  ./tools/regen.sh masks.psd --church-density 0.3
set -euo pipefail
cd "$(dirname "$0")"
MASKS="${1:-masks.psd}"; [ $# -gt 0 ] && shift
ARGS=()
if [ -e "$MASKS" ]; then ARGS+=(--masks "$MASKS"); else echo "маски не найдены ($MASKS) — используются черновые (автодетект)"; fi
# отдельные PNG-слои поверх PSD (имя файла = имя слоя, напр. water.flow.png) — поздние переопределяют PSD
[ -d masks_extra ] && ARGS+=(--masks masks_extra)
venv/bin/python3 gen_scene.py reference.jpg "${ARGS[@]}" \
    -o ../plugin/org.user.asciistreet/contents/ui/scene.js \
    --geometry geometry.json --cols 320 --preview /tmp/ascii-street-preview.png "$@"
echo "превью: /tmp/ascii-street-preview.png"
