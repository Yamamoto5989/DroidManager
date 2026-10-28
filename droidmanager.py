#!/usr/bin/env python3
"""
DroidManager
複数のAndroid端末をScrcpyで一括管理するUbuntu向けGUI (Tkinter / 標準ライブラリのみ)

必要なもの:
    sudo apt install python3-tk android-tools-adb scrcpy
    (推奨: python3-gi gir1.2-gtk-3.0 zenity)

Windows: Python(Tk同梱) + scrcpy公式のWindows版(adb同梱)をPATHに通すか、
         このファイルと同じフォルダに置く。
"""

import glob
import os
import posixpath
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_TITLE = "DroidManager"

IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
# Windowsでadb/scrcpy実行時にコンソール窓が一瞬出るのを防ぐ
NOWIN = {"creationflags": 0x08000000} if IS_WIN else {}
# 子プロセスの出力はUTF-8で読む (Windowsの既定cp932だと日本語名が化けるため)
TEXT = {"encoding": "utf-8", "errors": "replace"}
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def find_tool(name):
    """PATH上、なければアプリと同じフォルダ(または scrcpy サブフォルダ)から探す"""
    found = shutil.which(name)
    if found:
        return found
    exe = name + (".exe" if IS_WIN else "")
    # アプリと同じフォルダ、または scrcpy* フォルダ(公式zipの展開名 scrcpy-win64-v3.x 等)の中
    pats = (os.path.join(APP_DIR, exe),
            os.path.join(APP_DIR, "scrcpy*", exe),
            os.path.join(APP_DIR, "scrcpy*", "*", exe))
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    if IS_WIN:
        # インストール直後など、起動元のPATHが古い場合に備え、レジストリの最新PATHでも探す
        try:
            import winreg
            parts = []
            for root, sub in ((winreg.HKEY_CURRENT_USER, "Environment"),
                              (winreg.HKEY_LOCAL_MACHINE,
                               r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
                try:
                    with winreg.OpenKey(root, sub) as k:
                        parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
                except OSError:
                    pass
            hit = shutil.which(name, path=os.pathsep.join(parts))
            if hit:
                return hit
        except Exception:  # noqa: BLE001
            pass
    return name


# ---------------------------------------------------------------------------
# PC側のファイル/フォルダ選択
#   1) Ubuntu標準のファイル選択ダイアログ (xdg-desktop-portal / GNOME)
#   2) zenity   3) Tk標準ダイアログ   の順に試す
# ---------------------------------------------------------------------------
# Tkのプロセスとは別プロセスでGTKを動かす (GTK_USE_PORTAL=1 でポータル経由=標準ダイアログ)
_PORTAL_HELPER = r'''
import os, sys
os.environ["GTK_USE_PORTAL"] = "1"
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    mode, title = sys.argv[1], sys.argv[2]
    flt = sys.argv[3:5]
    action = (Gtk.FileChooserAction.SELECT_FOLDER if mode == "dir"
              else Gtk.FileChooserAction.OPEN)
    dlg = Gtk.FileChooserNative.new(title, None, action, "選択(_S)", "キャンセル(_C)")
    if mode == "multi":
        dlg.set_select_multiple(True)
    if len(flt) == 2:
        f = Gtk.FileFilter(); f.set_name(flt[0]); f.add_pattern(flt[1]); dlg.add_filter(f)
        a = Gtk.FileFilter(); a.set_name("すべてのファイル"); a.add_pattern("*"); dlg.add_filter(a)
    res = dlg.run()
    if res == Gtk.ResponseType.ACCEPT:
        print("\n".join(dlg.get_filenames()))
        sys.exit(0)
    sys.exit(1)          # キャンセル
except Exception as e:   # PyGObject未導入など → 呼び出し側でフォールバック
    sys.stderr.write(str(e))
    sys.exit(2)
'''


def _portal(mode, title, patterns=None):
    """OS標準ダイアログ。戻り値: 選択パスのリスト / キャンセル時は [] / 使えない時は None"""
    if not IS_LINUX:
        return None
    py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
    args = [py, "-c", _PORTAL_HELPER, mode, title] + (list(patterns) if patterns else [])
    try:
        r = subprocess.run(args, capture_output=True, **TEXT)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode == 0:
        return [p for p in r.stdout.splitlines() if p]
    if r.returncode == 1:
        return []
    return None


def _zenity(args):
    """zenityを実行。戻り値: 選択パスのリスト / キャンセル時は [] / 使えない時は None"""
    z = shutil.which("zenity") if IS_LINUX else None
    if not z:
        return None
    try:
        r = subprocess.run([z, "--file-selection", "--separator=\n"] + args,
                           capture_output=True, **TEXT)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode == 0:
        return [p for p in r.stdout.splitlines() if p]
    if r.returncode == 1:      # キャンセル
        return []
    return None                # その他のエラー → Tkにフォールバック


def pick_files(title, multiple=True, patterns=None):
    """ファイル選択。patterns例: ("APK", "*.apk")。戻り値: パスのリスト(キャンセルは空)"""
    res = _portal("multi" if multiple else "open", title, patterns)
    if res is not None:
        return res
    args = [f"--title={title}"]
    if multiple:
        args.append("--multiple")
    if patterns:
        args.append(f"--file-filter={patterns[0]} | {patterns[1]}")
        args.append("--file-filter=すべてのファイル | *")
    res = _zenity(args)
    if res is not None:
        return res
    ft = [patterns, ("All", "*.*")] if patterns else None
    if multiple:
        return list(filedialog.askopenfilenames(title=title, filetypes=ft or []))
    p = filedialog.askopenfilename(title=title, filetypes=ft or [])
    return [p] if p else []


def pick_dir(title):
    """フォルダ選択。戻り値: パス文字列 / キャンセル時は空文字"""
    res = _portal("dir", title)
    if res is None:
        res = _zenity(["--directory", f"--title={title}"])
    if res is not None:
        return res[0] if res else ""
    return filedialog.askdirectory(title=title) or ""


class RemoteBrowser(tk.Toplevel):
    """スマホ内のフォルダ/ファイルをGUIで選ぶダイアログ (adb shell ls を利用)。

    mode="dir"   : 保存先フォルダを選ぶ (PC→スマホ用)
    mode="files" : 取得するファイル/フォルダを複数選ぶ (スマホ→PC用)
    result       : (serial, [リモートパス, ...]) / キャンセル時は None
    """

    QUICK = (("内部ストレージ", "/sdcard"), ("Download", "/sdcard/Download"),
             ("DCIM", "/sdcard/DCIM"), ("Pictures", "/sdcard/Pictures"),
             ("ルート /", "/"))

    def __init__(self, app, serials, mode, title, start="/sdcard"):
        super().__init__(app)
        self.app = app
        self.mode = mode
        self.result = None
        self.path = start
        self.entries = []          # [(name, is_dir)]
        self.title(title)
        self.geometry("640x540")
        self.minsize(520, 420)
        self.transient(app)

        # デバイス選択
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(top, text="端末").pack(side="left")
        self.serial_var = tk.StringVar(value=serials[0])
        cb = ttk.Combobox(top, textvariable=self.serial_var, values=list(serials),
                          state="readonly" if len(serials) > 1 else "disabled", width=30)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.load(self.path))
        if mode == "files" and len(serials) > 1:
            ttk.Label(top, text="(取得は1台ずつ)").pack(side="left")

        # クイック移動
        quick = ttk.Frame(self)
        quick.pack(fill="x", padx=8, pady=2)
        for text, p in self.QUICK:
            ttk.Button(quick, text=text, command=lambda p=p: self.load(p)).pack(side="left", padx=2)

        # パス欄
        pb = ttk.Frame(self)
        pb.pack(fill="x", padx=8, pady=2)
        ttk.Button(pb, text="↑ 上へ", command=self.go_up).pack(side="left")
        self.path_var = tk.StringVar(value=start)
        pe = ttk.Entry(pb, textvariable=self.path_var)
        pe.pack(side="left", fill="x", expand=True, padx=4)
        pe.bind("<Return>", lambda e: self.load(self.path_var.get().strip() or "/"))
        ttk.Button(pb, text="移動", command=lambda: self.load(self.path_var.get().strip() or "/")
                   ).pack(side="left")
        ttk.Button(pb, text="更新", command=lambda: self.load(self.path)).pack(side="left", padx=(4, 0))

        # 一覧
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree = ttk.Treeview(mid, columns=("name", "kind"), show="headings",
                                 selectmode="extended" if mode == "files" else "browse")
        self.tree.heading("name", text="名前")
        self.tree.heading("kind", text="種類")
        self.tree.column("name", width=440, anchor="w")
        self.tree.column("kind", width=80, anchor="w")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Return>", self._on_double)

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status, foreground="#a00").pack(fill="x", padx=8)

        # ボタン
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=8, pady=8)
        if mode == "dir":
            ttk.Button(bt, text="新規フォルダ…", command=self.mkdir).pack(side="left")
            ttk.Button(bt, text="このフォルダに保存", command=self.choose_current
                       ).pack(side="right")
        else:
            ttk.Button(bt, text="このフォルダ全体を取得", command=self.choose_current
                       ).pack(side="left")
            ttk.Button(bt, text="選択した項目を取得", command=self.choose_selected
                       ).pack(side="right")
        ttk.Button(bt, text="キャンセル", command=self.destroy).pack(side="right", padx=6)

        self.load(start)
        self.grab_set()
        self.focus_set()

    # --- 内部処理
    def _ls(self, path):
        serial = self.serial_var.get()
        rc, out = self.app.adb_run(serial, "shell", f"ls -1ApL {shlex.quote(path)}", timeout=20)
        entries = []
        for line in out.splitlines():
            line = line.rstrip("\r")
            if not line or line.startswith("ls:"):
                continue
            if line.endswith("/"):
                entries.append((line[:-1], True))
            else:
                entries.append((line, False))
        if not entries and rc != 0:
            return None, out
        entries.sort(key=lambda e: (not e[1], e[0].lower()))
        return entries, ""

    def load(self, path):
        path = posixpath.normpath(path) if path else "/"
        entries, err = self._ls(path)
        if entries is None:
            self.status.set(f"開けません: {path}  {err[:80]}")
            self.path_var.set(self.path)
            return
        self.status.set("")
        self.path = path
        self.path_var.set(path)
        self.entries = entries
        self.tree.delete(*self.tree.get_children())
        for i, (name, is_dir) in enumerate(entries):
            self.tree.insert("", "end", iid=str(i),
                             values=(("📁 " if is_dir else "📄 ") + name,
                                     "フォルダ" if is_dir else "ファイル"))

    def go_up(self):
        self.load(posixpath.dirname(self.path.rstrip("/")) or "/")

    def _on_double(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        name, is_dir = self.entries[int(sel[0])]
        if is_dir:
            self.load(posixpath.join(self.path, name))

    def mkdir(self):
        name = simpledialog.askstring("新規フォルダ", "フォルダ名:", parent=self)
        if not name:
            return
        target = posixpath.join(self.path, name)
        rc, out = self.app.adb_run(self.serial_var.get(), "shell",
                                   f"mkdir -p {shlex.quote(target)}", timeout=20)
        if rc != 0:
            self.status.set(f"作成失敗: {out[:80]}")
            return
        self.load(target)

    def choose_current(self):
        self.result = (self.serial_var.get(), [self.path])
        self.destroy()

    def choose_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "取得するファイル/フォルダを選択してください。", parent=self)
            return
        paths = [posixpath.join(self.path, self.entries[int(i)][0]) for i in sel]
        self.result = (self.serial_var.get(), paths)
        self.destroy()


class Device:
    def __init__(self, serial, state, model=""):
        self.serial = serial
        self.state = state
        self.model = model


class App(tk.Tk):
    def __init__(self):
        super().__init__(className="Droidmanager")   # WM_CLASS=Droidmanager (.desktopのStartupWMClassと一致させる)
        self.title(APP_TITLE)
        self._set_icon()
        self.geometry("1020x800")
        self.minsize(860, 600)

        self.devices = {}       # serial -> Device
        self.procs = {}         # serial -> subprocess.Popen (scrcpy)
        self.log_queue = queue.Queue()

        self.adb = find_tool("adb")
        self.scrcpy = find_tool("scrcpy")
        self.scrcpy_major = self._detect_scrcpy_major()

        self._build_vars()
        self._build_ui()
        self._check_tools()
        self.refresh_devices()
        self.after(200, self._drain_log)
        self.after(1000, self._poll_procs)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ 初期化補助
    def _set_icon(self):
        here = os.path.dirname(os.path.abspath(__file__))
        cands = (os.path.join(here, "droidmanager.png"),
                 os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/droidmanager.png"))
        for p in cands:
            if os.path.exists(p):
                try:
                    self._icon = tk.PhotoImage(file=p)
                    self.iconphoto(True, self._icon)
                except tk.TclError:
                    pass
                break

    def _detect_scrcpy_major(self):
        """scrcpyのメジャーバージョンを取得 (取得できなければ新しい版とみなす)"""
        try:
            r = subprocess.run([self.scrcpy, "--version"], capture_output=True,
                               timeout=10, **TEXT, **NOWIN)
            m = re.search(r"scrcpy\s+(\d+)\.", r.stdout + r.stderr)
            if m:
                return int(m.group(1))
        except Exception:  # noqa: BLE001
            pass
        return 99

    # ------------------------------------------------------------------ UI
    def _build_vars(self):
        self.v_maxsize = tk.StringVar(value="1024")
        self.v_bitrate = tk.StringVar(value="8M")
        self.v_fps = tk.StringVar(value="60")
        self.v_noaudio = tk.BooleanVar(value=True)
        self.v_awake = tk.BooleanVar(value=False)
        self.v_screenoff = tk.BooleanVar(value=False)
        self.v_top = tk.BooleanVar(value=False)
        self.v_noborder = tk.BooleanVar(value=False)
        self.v_readonly = tk.BooleanVar(value=False)
        self.v_tile = tk.BooleanVar(value=True)
        self.v_cols = tk.StringVar(value="3")
        self.v_winw = tk.StringVar(value="480")
        self.v_winh = tk.StringVar(value="860")
        self.v_extra = tk.StringVar(value="")
        self.v_auto = tk.BooleanVar(value=False)
        self.v_text = tk.StringVar(value="")
        self.v_ip = tk.StringVar(value="")

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # ---- 端末リスト
        top = ttk.LabelFrame(self, text="接続中の端末 (Ctrl/Shiftで複数選択)")
        top.pack(fill="both", expand=True, **pad)

        cols = ("serial", "model", "state", "scrcpy")
        self.tree = ttk.Treeview(top, columns=cols, show="headings",
                                 selectmode="extended", height=8)
        for c, t, w in (("serial", "シリアル / アドレス", 240),
                        ("model", "モデル", 220),
                        ("state", "ADB状態", 120),
                        ("scrcpy", "Scrcpy", 120)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ---- 操作ボタン
        bar = ttk.Frame(self)
        bar.pack(fill="x", **pad)
        for text, cmd in (
            ("更新", self.refresh_devices),
            ("全選択", self.select_all),
            ("選択を起動", lambda: self.start_scrcpy(self.selected())),
            ("全て起動", lambda: self.start_scrcpy(self.ready_serials())),
            ("選択を停止", lambda: self.stop_scrcpy(self.selected())),
            ("全て停止", lambda: self.stop_scrcpy(list(self.procs))),
        ):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=3)
        ttk.Checkbutton(bar, text="2秒ごとに自動更新", variable=self.v_auto,
                        command=self._auto_toggle).pack(side="right")

        # ---- 設定
        opt = ttk.LabelFrame(self, text="Scrcpy オプション")
        opt.pack(fill="x", **pad)

        r1 = ttk.Frame(opt)
        r1.pack(fill="x", padx=6, pady=3)
        for label, var, w in (("最大解像度", self.v_maxsize, 7),
                              ("ビットレート", self.v_bitrate, 7),
                              ("最大FPS", self.v_fps, 5)):
            ttk.Label(r1, text=label).pack(side="left")
            ttk.Entry(r1, textvariable=var, width=w).pack(side="left", padx=(2, 12))

        r2 = ttk.Frame(opt)
        r2.pack(fill="x", padx=6, pady=3)
        for text, var in (("音声オフ", self.v_noaudio),
                          ("画面スリープ防止", self.v_awake),
                          ("端末画面を消灯", self.v_screenoff),
                          ("常に手前", self.v_top),
                          ("枠なし", self.v_noborder),
                          ("閲覧のみ(操作不可)", self.v_readonly)):
            ttk.Checkbutton(r2, text=text, variable=var).pack(side="left", padx=4)

        r3 = ttk.Frame(opt)
        r3.pack(fill="x", padx=6, pady=3)
        ttk.Checkbutton(r3, text="ウィンドウを自動タイル配置", variable=self.v_tile
                        ).pack(side="left")
        for label, var in (("列数", self.v_cols), ("幅", self.v_winw), ("高さ", self.v_winh)):
            ttk.Label(r3, text=label).pack(side="left", padx=(10, 0))
            ttk.Entry(r3, textvariable=var, width=5).pack(side="left", padx=2)
        ttk.Label(r3, text="追加引数").pack(side="left", padx=(14, 0))
        ttk.Entry(r3, textvariable=self.v_extra, width=28).pack(side="left", padx=2)

        # ---- 一括操作
        bulk = ttk.LabelFrame(self, text="選択端末への一括操作 (ADB)")
        bulk.pack(fill="x", **pad)

        b1 = ttk.Frame(bulk)
        b1.pack(fill="x", padx=6, pady=3)
        for text, key in (("ホーム", "KEYCODE_HOME"), ("戻る", "KEYCODE_BACK"),
                          ("アプリ履歴", "KEYCODE_APP_SWITCH"),
                          ("電源", "KEYCODE_POWER"),
                          ("音量+", "KEYCODE_VOLUME_UP"),
                          ("音量-", "KEYCODE_VOLUME_DOWN")):
            ttk.Button(b1, text=text,
                       command=lambda k=key: self.bulk_keyevent(k)).pack(side="left", padx=2)
        ttk.Button(b1, text="APKインストール…", command=self.bulk_install
                   ).pack(side="left", padx=(12, 2))
        ttk.Button(b1, text="スクショ保存…", command=self.bulk_screenshot
                   ).pack(side="left", padx=2)

        b2 = ttk.Frame(bulk)
        b2.pack(fill="x", padx=6, pady=3)
        ttk.Label(b2, text="テキスト入力").pack(side="left")
        ent = ttk.Entry(b2, textvariable=self.v_text, width=30)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: self.bulk_text())
        ttk.Button(b2, text="送信", command=self.bulk_text).pack(side="left")

        b3 = ttk.Frame(bulk)
        b3.pack(fill="x", padx=6, pady=3)
        ttk.Label(b3, text="Wi-Fi接続 IP[:port]").pack(side="left")
        ttk.Entry(b3, textvariable=self.v_ip, width=22).pack(side="left", padx=4)
        ttk.Button(b3, text="接続", command=self.wifi_connect).pack(side="left", padx=2)
        ttk.Button(b3, text="切断", command=self.wifi_disconnect).pack(side="left", padx=2)
        ttk.Button(b3, text="選択端末をWi-Fi(tcpip)化", command=self.wifi_enable
                   ).pack(side="left", padx=(12, 2))

        # ---- ファイル転送
        ft = ttk.LabelFrame(self, text="ファイル転送 (ADB)")
        ft.pack(fill="x", **pad)
        f1 = ttk.Frame(ft)
        f1.pack(fill="x", padx=6, pady=4)
        ttk.Button(f1, text="PC → スマホ (ファイル選択)…",
                   command=lambda: self.transfer_push(False)).pack(side="left", padx=2)
        ttk.Button(f1, text="PC → スマホ (フォルダ選択)…",
                   command=lambda: self.transfer_push(True)).pack(side="left", padx=2)
        ttk.Button(f1, text="スマホ → PC…", command=self.transfer_pull
                   ).pack(side="left", padx=(14, 2))
        ttk.Label(f1, text="送信: 選択した全端末へ / 取得: 1台ずつ").pack(side="left", padx=10)

        # ---- ログ
        lf = ttk.LabelFrame(self, text="ログ")
        lf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(lf, height=9, state="disabled", wrap="none")
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")

    # ------------------------------------------------------------- helpers
    def write_log(self, msg):
        self.log_queue.put(msg)

    def _drain_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg.rstrip("\n") + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._drain_log)

    def _check_tools(self):
        missing = [n for n, p in (("adb", self.adb), ("scrcpy", self.scrcpy))
                   if not shutil.which(p)]
        if missing:
            if IS_WIN:
                hint = ("scrcpy公式のWindows版(adb同梱)を展開し、PATHに追加するか、\n"
                        "このアプリと同じフォルダに置いてください。")
            else:
                hint = "sudo apt install android-tools-adb scrcpy\nでインストールしてください。"
            messagebox.showwarning(
                APP_TITLE,
                "次のコマンドが見つかりません: " + ", ".join(missing) + "\n\n" + hint)

    def selected(self):
        return list(self.tree.selection())

    def ready_serials(self):
        return [s for s, d in self.devices.items() if d.state == "device"]

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def run_async(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    def adb_run(self, serial, *args, timeout=60):
        cmd = [self.adb] + (["-s", serial] if serial else []) + list(args)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, **TEXT, **NOWIN)
            out = (r.stdout + r.stderr).strip()
            return r.returncode, out
        except Exception as e:  # noqa: BLE001
            return 1, str(e)

    # ------------------------------------------------------------- devices
    def refresh_devices(self):
        self.run_async(self._refresh_worker)

    def _refresh_worker(self):
        rc, out = self.adb_run(None, "devices", "-l", timeout=15)
        devs = {}
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            m = re.search(r"model:(\S+)", line)
            devs[serial] = Device(serial, state, m.group(1) if m else "")
        self.after(0, self._apply_devices, devs)

    def _apply_devices(self, devs):
        self.devices = devs
        sel = set(self.selected())
        self.tree.delete(*self.tree.get_children())
        for s, d in devs.items():
            self.tree.insert("", "end", iid=s,
                             values=(s, d.model, d.state, self._proc_state(s)))
        keep = [s for s in sel if s in devs]
        if keep:
            self.tree.selection_set(keep)

    def _proc_state(self, serial):
        p = self.procs.get(serial)
        return "実行中" if p and p.poll() is None else "-"

    def _auto_toggle(self):
        if self.v_auto.get():
            self._auto_loop()

    def _auto_loop(self):
        if self.v_auto.get():
            self.refresh_devices()
            self.after(2000, self._auto_loop)

    def _poll_procs(self):
        changed = False
        for s, p in list(self.procs.items()):
            if p.poll() is not None:
                self.write_log(f"[{s}] scrcpy 終了 (code {p.returncode})")
                del self.procs[s]
                changed = True
        if changed:
            self._apply_devices(self.devices)
        self.after(1000, self._poll_procs)

    # -------------------------------------------------------------- scrcpy
    def _int(self, var, default):
        try:
            return int(var.get())
        except ValueError:
            return default

    def build_scrcpy_cmd(self, serial, index):
        cmd = [self.scrcpy, "-s", serial,
               "--window-title", f"{serial} ({self.devices[serial].model or 'Android'})"]
        if self.v_maxsize.get().strip():
            cmd += ["--max-size", self.v_maxsize.get().strip()]
        if self.v_bitrate.get().strip():
            # scrcpy 1.x は --bit-rate、2.0以降は --video-bit-rate
            flag = "--video-bit-rate" if self.scrcpy_major >= 2 else "--bit-rate"
            cmd += [flag, self.v_bitrate.get().strip()]
        if self.v_fps.get().strip():
            cmd += ["--max-fps", self.v_fps.get().strip()]
        if self.v_noaudio.get() and self.scrcpy_major >= 2:   # 1.xには音声転送自体がない
            cmd.append("--no-audio")
        if self.v_awake.get():
            cmd.append("--stay-awake")
        if self.v_screenoff.get():
            cmd.append("--turn-screen-off")
        if self.v_top.get():
            cmd.append("--always-on-top")
        if self.v_noborder.get():
            cmd.append("--window-borderless")
        if self.v_readonly.get():
            cmd.append("--no-control")
        if self.v_tile.get():
            cols = max(1, self._int(self.v_cols, 3))
            w = max(100, self._int(self.v_winw, 480))
            h = max(100, self._int(self.v_winh, 860))
            x = (index % cols) * w
            y = (index // cols) * h
            cmd += ["--window-x", str(x), "--window-y", str(y),
                    "--window-width", str(w), "--window-height", str(h)]
        extra = self.v_extra.get().strip()
        if extra:
            cmd += extra.split()
        return cmd

    def start_scrcpy(self, serials):
        serials = [s for s in serials if s in self.devices
                   and self.devices[s].state == "device"]
        if not serials:
            messagebox.showinfo(APP_TITLE, "起動できる端末がありません。")
            return
        index = len([p for p in self.procs.values() if p.poll() is None])
        for s in serials:
            if s in self.procs and self.procs[s].poll() is None:
                self.write_log(f"[{s}] 既に実行中")
                continue
            cmd = self.build_scrcpy_cmd(s, index)
            self.write_log("$ " + " ".join(cmd))
            try:
                kw = dict(NOWIN) if IS_WIN else {"start_new_session": True}
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, **TEXT, **kw)
            except Exception as e:  # noqa: BLE001
                self.write_log(f"[{s}] 起動失敗: {e}")
                continue
            self.procs[s] = p
            index += 1
            self.run_async(self._pipe_log, s, p)
        self._apply_devices(self.devices)

    def _pipe_log(self, serial, proc):
        for line in proc.stdout:
            self.write_log(f"[{serial}] {line.rstrip()}")

    def stop_scrcpy(self, serials):
        for s in serials:
            p = self.procs.get(s)
            if p and p.poll() is None:
                try:
                    if IS_WIN:
                        p.terminate()
                    else:
                        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                except Exception:  # noqa: BLE001
                    p.terminate()
                self.write_log(f"[{s}] 停止要求")
        self.after(500, lambda: self._apply_devices(self.devices))

    # ---------------------------------------------------------- bulk (ADB)
    def _need_selection(self):
        sel = [s for s in self.selected()
               if s in self.devices and self.devices[s].state == "device"]
        if not sel:
            messagebox.showinfo(APP_TITLE, "操作対象の端末を選択してください。")
        return sel

    def _bulk(self, label, func):
        sel = self._need_selection()
        if not sel:
            return

        def work(s):
            rc, out = func(s)
            self.write_log(f"[{s}] {label}: {'OK' if rc == 0 else 'NG'} {out[:300]}")

        for s in sel:
            self.run_async(work, s)

    def bulk_keyevent(self, key):
        self._bulk(key, lambda s: self.adb_run(s, "shell", "input", "keyevent", key))

    def bulk_text(self):
        text = self.v_text.get()
        if not text:
            return
        # adb shell input text はスペースを %s、記号をエスケープする必要がある
        esc = re.sub(r"([\\'\"&|<>();$`!*?\[\]{}~#^])", r"\\\1", text).replace(" ", "%s")
        self._bulk("テキスト入力",
                   lambda s: self.adb_run(s, "shell", "input", "text", esc))

    def bulk_install(self):
        picked = pick_files("APKを選択", multiple=False, patterns=("APK", "*.apk"))
        if not picked:
            return
        path = picked[0]
        self._bulk("APKインストール",
                   lambda s: self.adb_run(s, "install", "-r", path, timeout=300))

    def bulk_screenshot(self):
        d = pick_dir("保存先フォルダ")
        if not d:
            return

        def shot(s):
            name = re.sub(r"[^\w.-]", "_", s)
            dst = os.path.join(d, f"{name}.png")
            try:
                with open(dst, "wb") as f:
                    r = subprocess.run([self.adb, "-s", s, "exec-out", "screencap", "-p"],
                                       stdout=f, stderr=subprocess.PIPE, timeout=30, **NOWIN)
                return r.returncode, dst
            except Exception as e:  # noqa: BLE001
                return 1, str(e)

        self._bulk("スクリーンショット", shot)

    # ------------------------------------------------------- ファイル転送
    @staticmethod
    def _last_line(out):
        lines = out.strip().splitlines()
        return lines[-1] if lines else ""

    def transfer_push(self, folder=False):
        """PC→スマホ: PCでファイル選択 → スマホ側の保存先を選択 → 送信"""
        sel = self._need_selection()
        if not sel:
            return
        if folder:
            d = pick_dir("スマホへ送るフォルダをPCから選択")
            local_paths = [d] if d else []
        else:
            local_paths = pick_files("スマホへ送るファイルをPCから選択")
        if not local_paths:
            return

        dlg = RemoteBrowser(self, sel, "dir", "スマホ側の保存先フォルダを選択",
                            start="/sdcard/Download")
        self.wait_window(dlg)
        if not dlg.result:
            return
        dest = dlg.result[1][0]
        dest_dir = dest.rstrip("/") + "/"

        def work(serial):
            for lp in local_paths:
                self.write_log(f"[{serial}] 送信中: {lp} → {dest_dir}")
                rc, out = self.adb_run(serial, "push", lp, dest_dir, timeout=3600)
                self.write_log(f"[{serial}] 送信 {'OK' if rc == 0 else 'NG'}: "
                               f"{os.path.basename(lp)}  {self._last_line(out)}")

        for s in sel:
            self.run_async(work, s)

    def transfer_pull(self):
        """スマホ→PC: スマホ側のファイルをGUIで選択 → PC側の保存先を選択 → 取得"""
        sel = self._need_selection()
        if not sel:
            return
        dlg = RemoteBrowser(self, sel, "files", "PCへ取得するスマホのファイル/フォルダを選択",
                            start="/sdcard")
        self.wait_window(dlg)
        if not dlg.result:
            return
        serial, remote_paths = dlg.result

        dest = pick_dir("PC側の保存先フォルダを選択")
        if not dest:
            return

        def work():
            for rp in remote_paths:
                self.write_log(f"[{serial}] 取得中: {rp} → {dest}")
                rc, out = self.adb_run(serial, "pull", rp, dest, timeout=3600)
                self.write_log(f"[{serial}] 取得 {'OK' if rc == 0 else 'NG'}: "
                               f"{posixpath.basename(rp.rstrip('/')) or rp}  "
                               f"{self._last_line(out)}")

        self.run_async(work)

    # ---------------------------------------------------------- Wi-Fi ADB
    def wifi_connect(self):
        ip = self.v_ip.get().strip()
        if not ip:
            return
        if ":" not in ip:
            ip += ":5555"

        def work():
            rc, out = self.adb_run(None, "connect", ip, timeout=20)
            self.write_log(f"adb connect {ip}: {out}")
            self._refresh_worker()

        self.run_async(work)

    def wifi_enable(self):
        sel = [s for s in self._need_selection() if ":" not in s]
        if not sel:
            return

        def work(s):
            rc, out = self.adb_run(s, "shell", "ip", "route")
            m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", out)
            self.adb_run(s, "tcpip", "5555")
            if m:
                ip = m.group(1)
                self.write_log(f"[{s}] tcpip 5555 設定。IP={ip} → 接続を試行")
                import time
                time.sleep(2)
                rc, out = self.adb_run(None, "connect", f"{ip}:5555", timeout=20)
                self.write_log(f"adb connect {ip}:5555: {out}")
            else:
                self.write_log(f"[{s}] IPアドレスを取得できませんでした")
            self._refresh_worker()

        for s in sel:
            self.run_async(work, s)

    def wifi_disconnect(self):
        sel = [s for s in self.selected() if ":" in s]
        if not sel:
            messagebox.showinfo(APP_TITLE, "Wi-Fi接続の端末(IP:port)を選択してください。")
            return

        def work(s):
            rc, out = self.adb_run(None, "disconnect", s)
            self.write_log(f"adb disconnect {s}: {out}")
            self._refresh_worker()

        for s in sel:
            self.run_async(work, s)

    # ---------------------------------------------------------------- exit
    def on_close(self):
        if any(p.poll() is None for p in self.procs.values()):
            if not messagebox.askyesno(APP_TITLE, "実行中のscrcpyを全て終了して閉じますか?"):
                return
            self.stop_scrcpy(list(self.procs))
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
