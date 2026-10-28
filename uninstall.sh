#!/usr/bin/env bash
# DroidManager アンインストーラー (apt で入れたパッケージは削除しません)
set -euo pipefail
PREFIX="${HOME}/.local"

rm -rf  "${PREFIX}/share/droidmanager"
rm -f   "${PREFIX}/bin/droidmanager"
rm -f   "${PREFIX}/share/applications/droidmanager.desktop"
rm -f   "${PREFIX}/share/icons/hicolor/scalable/apps/droidmanager.svg"
rm -f   "${PREFIX}/share/icons/hicolor/256x256/apps/droidmanager.png"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${PREFIX}/share/applications" || true
command -v gtk-update-icon-cache  >/dev/null 2>&1 && gtk-update-icon-cache -f -t "${PREFIX}/share/icons/hicolor" >/dev/null 2>&1 || true
echo "DroidManager を削除しました。"
