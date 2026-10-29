
#!/usr/bin/env bash
set -euo pipefail

REPO="DroidManager"
OWNER="Yamamoto5989"
BASE_URL="https://reprox.dev/${OWNER}/${REPO}"

echo "DroidManager: セットアップを開始します"

# 必要なツールを準備
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# APT署名鍵を取得
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL "${BASE_URL}/public.key" |
    gpg --dearmor |
    sudo tee "/etc/apt/keyrings/droidmanager.gpg" >/dev/null
sudo chmod 0644 /etc/apt/keyrings/droidmanager.gpg

# APTリポジトリを登録
sudo tee "/etc/apt/sources.list.d/droidmanager.sources" >/dev/null <<EOF
Types: deb
URIs: ${BASE_URL}
Suites: stable
Components: main
Signed-By: /etc/apt/keyrings/droidmanager.gpg
EOF

# インストール
sudo apt-get update
sudo apt-get install -y droidmanager

echo "DroidManagerのインストールが完了しました！"
