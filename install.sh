#!/usr/bin/env bash
# DroidManager インストーラー (Ubuntu / Debian系)
#   ./install.sh            : パッケージ導入 + 自分のユーザーにインストール (~/.local)
#   SKIP_APT=1 ./install.sh : パッケージ導入をスキップ
set -euo pipefail

APP=droidmanager
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/.local"
APPDIR="${PREFIX}/share/${APP}"

# ---- 1. 必要パッケージ -------------------------------------------------------
REQUIRED=(python3 python3-tk android-tools-adb scrcpy)
RECOMMENDED=(python3-gi gir1.2-gtk-3.0 zenity android-sdk-platform-tools-common)

if [ "${SKIP_APT:-0}" != "1" ]; then
  echo "==> 必要なパッケージをインストールします (sudo のパスワードを求められます)"
  sudo apt-get update
  sudo apt-get install -y "${REQUIRED[@]}"
  echo "==> 推奨パッケージ (OS標準のファイル選択ダイアログ / USB権限) を導入します"
  for pkg in "${RECOMMENDED[@]}"; do
    sudo apt-get install -y "$pkg" || echo "   (スキップ: $pkg)"
  done
fi

# ---- 2. ファイル配置 ---------------------------------------------------------
echo "==> ${APPDIR} にインストールします"
mkdir -p "${APPDIR}" "${PREFIX}/bin" "${PREFIX}/share/applications" \
         "${PREFIX}/share/icons/hicolor/scalable/apps" \
         "${PREFIX}/share/icons/hicolor/256x256/apps"

install -m 755 "${SRC}/droidmanager.py" "${APPDIR}/droidmanager.py"
install -m 644 "${SRC}/droidmanager.png" "${APPDIR}/droidmanager.png"
install -m 644 "${SRC}/droidmanager.svg" "${PREFIX}/share/icons/hicolor/scalable/apps/droidmanager.svg"
install -m 644 "${SRC}/droidmanager.png" "${PREFIX}/share/icons/hicolor/256x256/apps/droidmanager.png"

# ---- 3. 起動コマンド (pyenv等の別Pythonではなくシステムのpython3を使う) --------
cat > "${PREFIX}/bin/droidmanager" <<EOF
#!/bin/sh
exec /usr/bin/python3 "${APPDIR}/droidmanager.py" "\$@"
EOF
chmod 755 "${PREFIX}/bin/droidmanager"

# ---- 4. アプリメニュー用 .desktop ---------------------------------------------
cat > "${PREFIX}/share/applications/droidmanager.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=DroidManager
GenericName=Android Device Manager
Comment=Scrcpyで複数のAndroid端末をまとめて管理
Exec=${PREFIX}/bin/droidmanager
Icon=droidmanager
Terminal=false
Categories=Utility;System;Development;
Keywords=android;scrcpy;adb;phone;スマホ;
StartupWMClass=Droidmanager
EOF
chmod 644 "${PREFIX}/share/applications/droidmanager.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${PREFIX}/share/applications" || true
command -v gtk-update-icon-cache  >/dev/null 2>&1 && gtk-update-icon-cache -f -t "${PREFIX}/share/icons/hicolor" >/dev/null 2>&1 || true

echo
echo "完了: アプリ一覧(アクティビティ → 'DroidManager')から起動できます。"
echo "      ターミナルからは  droidmanager  でも起動できます。"
echo "      (表示されない場合は一度ログアウト/ログインしてください)"
