# DroidManager

ADBとScrcpyを使って複数のAndroidデバイスを管理するソフトウェアです。WindowsとDebianで動作します。

## Debianで使う
```
sudo apt install droidmanager
```
またわ
```
unzip droidmanager.zip
cd droidmanager
./install.sh
```

アプリ一覧に「DroidManager」が追加されます。ターミナルからは `droidmanager` でも起動できます。
削除は `./uninstall.sh`(aptで入れたパッケージは残ります)。

## 必要なパッケージ (Debian)

| パッケージ | 区分 | 用途 |
|---|---|---|
| `python3` | 必須 | 本体の実行 |
| `python3-tk` | 必須 | GUI (Tkinter) |
| `android-tools-adb` | 必須 | 端末の検出・ファイル転送・一括操作 |
| `scrcpy` | 必須 | 画面ミラーリング・操作 |
| `python3-gi` | 推奨 | OS標準のファイル選択ダイアログ |
| `gir1.2-gtk-3.0` | 推奨 | 同上 |
| `zenity` | 推奨 | 上記が使えない場合の代替ダイアログ |
| `android-sdk-platform-tools-common` | 推奨 | USB接続時の権限設定 (udevルール) |

手動で入れる場合:

```
sudo apt install python3 python3-tk android-tools-adb scrcpy
sudo apt install python3-gi gir1.2-gtk-3.0 zenity android-sdk-platform-tools-common
```



## Windows で使う

1. zip を展開する
2. `install_windows.bat` をダブルクリック

不足している **Python** と **scrcpy** (と、必要なら adb) は、確認のうえ `winget` (Windows 10/11 標準) で自動インストールします。
そのあと `%LOCALAPPDATA%\DroidManager` にコピーされ、スタートメニューに「DroidManager」が追加されます
(スタートで `DroidManager` と検索、右クリックでタスクバーにピン留めも可能)。

| 自動で入るもの | winget のパッケージID |
|---|---|
| Python 3.12 (Tk同梱) | `Python.Python.3.12` |
| scrcpy | `Genymobile.scrcpy` |
| adb (scrcpyに無い場合のみ) | `Google.PlatformTools` |

wingetが無い場合は、[python.org](https://www.python.org/downloads/windows/) のPythonと
[scrcpy公式のWindows版](https://github.com/Genymobile/scrcpy/releases) (adb同梱) を手動で入れてください。
展開した scrcpy のフォルダを、この `droidmanager` フォルダの中に置いてもかまいません。

削除は `uninstall_windows.bat` です(PythonとscrcpyはWindows側に残ります)。
インストールせずに試すだけなら `DroidManager.bat` をダブルクリックします。

## 補足

- scrcpy が 1.x の場合、音声オフ(`--no-audio`)は自動的に省略し、ビットレートは `--bit-rate` で渡します。
  音声転送など新しい機能を使うなら scrcpy 2.0 以降を使ってください。
- 端末側で「USBデバッグ」を有効にし、初回接続時に表示される許可ダイアログを承認してください。
