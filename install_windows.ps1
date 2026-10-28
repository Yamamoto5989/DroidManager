$ErrorActionPreference = "Stop"

# DroidManager Windows用インストーラー
#   1. 不足している Python / scrcpy / adb を winget で自動インストール (確認あり)
#   2. %LOCALAPPDATA%\DroidManager にコピー
#   3. スタートメニューにショートカットを作成

$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$dst = Join-Path $env:LOCALAPPDATA "DroidManager"

function Update-SessionPath {
    $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $u = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$m;$u"
}

function Find-Python {
    foreach ($n in "pyw.exe", "pythonw.exe") {
        $c = Get-Command $n -ErrorAction SilentlyContinue
        if ($c) { return $c.Source }
    }
    return $null
}

function Find-Tool([string]$name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    # このフォルダに置かれた scrcpy* フォルダ (公式zip展開) の中も探す
    $f = Get-ChildItem -Path $src -Recurse -Depth 2 -Filter $name -ErrorAction SilentlyContinue |
         Select-Object -First 1
    if ($f) { return $f.FullName }
    return $null
}

function Install-WithWinget([string]$id) {
    Write-Host "    winget install $id"
    winget install -e --id $id --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Write-Warning "$id のインストールが完了しなかった可能性があります (終了コード $LASTEXITCODE)" }
}

# ---- 1. 必要なものの確認 ------------------------------------------------------
$need = @()
if (-not (Find-Python))              { $need += @{ Name = "Python"; Id = "Python.Python.3.12" } }
if (-not (Find-Tool "scrcpy.exe"))   { $need += @{ Name = "scrcpy"; Id = "Genymobile.scrcpy" } }

if ($need.Count -gt 0) {
    Write-Host ("不足しているもの: " + (($need | ForEach-Object { $_.Name }) -join ", "))
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "winget が見つかりません。Python (python.org) と scrcpy公式Windows版を手動でインストールしてから、もう一度実行してください。"
    }
    $ans = Read-Host "winget で自動インストールしますか? [Y/n]"
    if ($ans -match '^[nN]') {
        throw "中止しました。必要なものを用意してから、もう一度実行してください。"
    }
    foreach ($p in $need) { Install-WithWinget $p.Id }
    Update-SessionPath
}

# adb は scrcpy に同梱されているが、見つからなければ Google の platform-tools を入れる
if (-not (Find-Tool "adb.exe")) {
    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        Install-WithWinget "Google.PlatformTools"
        Update-SessionPath
    } else {
        Write-Warning "adb が見つかりません。scrcpy公式Windows版(adb同梱)を使うか、platform-toolsをPATHに追加してください。"
    }
}

$py = Find-Python
if (-not $py) {
    throw "Python (pyw.exe / pythonw.exe) が見つかりません。インストール後に新しいウィンドウでもう一度実行してください。"
}

# ---- 2. ファイル配置 ----------------------------------------------------------
# 再インストール時、実行中の DroidManager / adb がファイルをロックしているので先に終了する
if (Test-Path $dst) {
    foreach ($adb in (Get-ChildItem -Path $dst -Recurse -Filter "adb.exe" -ErrorAction SilentlyContinue)) {
        try { & $adb.FullName kill-server 2>$null | Out-Null } catch {}
    }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($dst, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine -like "*$dst*droidmanager.py*")
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

Write-Host "==> $dst にインストールします"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
foreach ($f in "droidmanager.py", "droidmanager.png", "droidmanager.ico") {
    Copy-Item -Path (Join-Path $src $f) -Destination $dst -Force
}

# 同じ場所に置いた scrcpy* フォルダ (公式Windows版を展開したもの) があれば一緒にコピー
Get-ChildItem -Path $src -Directory -Filter "scrcpy*" | ForEach-Object {
    $target = Join-Path $dst $_.Name
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $_.FullName "*") -Destination $target -Recurse -Force
    Write-Host "    コピー: $($_.Name)"
}

# ---- 3. スタートメニューのショートカット -----------------------------------------
$programs = [Environment]::GetFolderPath("Programs")
$lnk = Join-Path $programs "DroidManager.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $py
$s.Arguments = '"' + (Join-Path $dst "droidmanager.py") + '"'
$s.WorkingDirectory = $dst
$s.IconLocation = (Join-Path $dst "droidmanager.ico")
$s.Description = "Scrcpyで複数のAndroid端末をまとめて管理"
$s.Save()

Write-Host ""
Write-Host "完了: スタートメニューの「DroidManager」から起動できます。"
Write-Host "      (スタートで 'DroidManager' と入力して検索、右クリックでタスクバーにピン留めも可能)"
