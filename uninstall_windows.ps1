$ErrorActionPreference = "Stop"

# DroidManager Windows用アンインストーラー (Pythonやscrcpyは削除しません)
$dst = Join-Path $env:LOCALAPPDATA "DroidManager"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "DroidManager.lnk"

if (Test-Path $lnk) { Remove-Item -Force $lnk }
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Write-Host "DroidManager を削除しました。"
