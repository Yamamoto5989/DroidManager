$ErrorActionPreference = "Stop"

# DroidManager Windows用アンインストーラー (Pythonやscrcpyの本体は削除しません)
$dst = Join-Path $env:LOCALAPPDATA "DroidManager"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "DroidManager.lnk"

function Stop-DroidManagerProcesses {
    # 1) インストール先の adb が常駐していれば止める (フォルダをロックするため)
    foreach ($adb in (Get-ChildItem -Path $dst -Recurse -Filter "adb.exe" -ErrorAction SilentlyContinue)) {
        try { & $adb.FullName kill-server 2>$null | Out-Null } catch {}
    }
    # 2) インストール先のexe、または droidmanager.py を実行中のプロセスを終了
    $targets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($dst, [StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine -like "*$dst*droidmanager.py*")
    }
    foreach ($p in $targets) {
        Write-Host "    終了: $($p.Name) (PID $($p.ProcessId))"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

if (Test-Path $lnk) { Remove-Item -Force $lnk }

if (Test-Path $dst) {
    Write-Host "==> 実行中の DroidManager / adb / scrcpy を終了します"
    Stop-DroidManagerProcesses

    $removed = $false
    for ($i = 1; $i -le 5; $i++) {
        try {
            Remove-Item -Recurse -Force $dst
            $removed = $true
            break
        } catch {
            Write-Host "    削除に失敗 ($i/5)。再試行します..."
            Start-Sleep -Seconds 2
            Stop-DroidManagerProcesses
        }
    }
    if (-not $removed) {
        Write-Warning "一部のファイルを削除できませんでした: $dst"
        Write-Warning "DroidManager・scrcpy・adb を閉じるか、PCを再起動してから、もう一度実行してください。"
        exit 1
    }
}
Write-Host "DroidManager を削除しました。"
