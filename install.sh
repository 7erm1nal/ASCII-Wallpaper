#!/usr/bin/env bash
# Установка плагина в ~/.local/share/plasma/wallpapers (Plasma 6)
set -euo pipefail
cd "$(dirname "$0")"
ID=org.user.asciistreet
kpackagetool6 -t Plasma/Wallpaper -u "plugin/$ID" || kpackagetool6 -t Plasma/Wallpaper -i "plugin/$ID"
echo "Готово. Настройки -> Экран блокировки -> Внешний вид: Настроить… -> Тип обоев: «ASCII Rainy Street»"
