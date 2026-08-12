# -*- coding: utf-8 -*-
# AiReLinkerServer.pyw - Lightweight receiver with Horizontal Dual-Pane Logging & Split Launcher
import os
import sys
import json
import datetime
import re
import base64
import threading
import subprocess
import winreg
import socket
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
import tkinter as tk
from tkinter import ttk, messagebox

# 🌟 【二重起動の防止機能 - ポート5001相互ロック】
# すでに1台目が起動している場合は手渡し通信を送り、自分自身はトレイを汚さずに静かに終了します
_mutex_socket = None
try:
    _mutex_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _mutex_socket.bind(('127.0.0.1', 5001))
    # 5001番ポートを自プロセスで占有ロックします
except OSError:
    # 5001がすでに占有されている ➡️ 起動中の1台目のサーバーにウィンドウ呼び出しを命令
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:5000/show", timeout=1)
    except:
        pass
    sys.exit(0)

# 🌟 必要な外部ライブラリを自動でチェックし、入っていなければ裏でインストールを試みます
def ensure_dependencies():
    try:
        import pystray
        from PIL import Image, ImageTk
    except ImportError:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pystray", "pillow"], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass

ensure_dependencies()

try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image, ImageTk
    HAS_SYSTRAY = True
except ImportError:
    HAS_SYSTRAY = False

def get_actual_path(base_path):
    # .pyw を優先的に探し、なければ .py を探す
    base, ext = os.path.splitext(base_path)
    path_pyw = base + ".pyw"
    if os.path.exists(path_pyw):
        return path_pyw
    path_py = base + ".py"
    if os.path.exists(path_py):
        return path_py
    return base_path # どちらもなければ元に戻す


# Windows特有の「Python標準アイコン化バグ」を回避するためのAppID登録
try:
    import ctypes
    myappid = 'airelinker.suite.server.v2'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

PORT = 5000
CONFIG_PATH = "./config.json"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
ICON_SERVER = os.path.join(CURRENT_DIR, "icon", "AiReLinker.ico")
MAIN_APP_PATH = get_actual_path(os.path.join(CURRENT_DIR, "AiReAnchorMain.py"))
CLEAT_APP_PATH = get_actual_path(os.path.join(CURRENT_DIR, "AiReCleat.pyw"))

server_suspended = False

def load_config_data():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def save_config_data(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except: pass

def load_save_dir():
    cfg = load_config_data()
    s_dir = cfg.get("save_dir", "")
    if s_dir and os.path.exists(s_dir):
        return os.path.normpath(s_dir)
    return os.path.join(CURRENT_DIR, "logs")

SAVE_DIR = load_save_dir()

def format_iso_to_plain(iso_str):
    if not iso_str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        clean = re.sub(r'\.\d+Z$', '', iso_str).replace('T', ' ').replace('Z', '')
        utc_dt = datetime.datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        jst_dt = utc_dt + datetime.timedelta(hours=9)
        return jst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return iso_str

def sanitize_filename(filename):
    if not filename:
        return "Untitled_Chat"
    clean_name = re.sub(r'[\\/*?:"<>|]', "_", filename)
    clean_name = re.sub(r'\s+', ' ', clean_name)
    clean_name = re.sub(r'_+', '_', clean_name)
    clean_name = clean_name.strip()
    clean_name = re.sub(r'[\s._]+$', '', clean_name)
    clean_name = re.sub(r'^[\s._]+', '', clean_name)
    if len(clean_name) > 100:
        clean_name = clean_name[:100]
        clean_name = re.sub(r'[\s._]+$', '', clean_name)
    return clean_name if clean_name else "Untitled_Chat"

# 🌟 【調停側ログの自動簡易化フィルター】
# 簡易モード時でも、チャット・ファイル新規作成ログは綺麗に整形して画面に残すようにアップデートしました
def simplify_cleat_message(msg):
    # 1. 会話差分のスマート変換
    m1 = re.search(r'総会話\s*(\d+)\s*件中、基準重複\s*(\d+)\s*件・同期重複\s*(\d+)\s*件.*新規\s*(\d+)\s*件', msg)
    if m1:
        total = m1.group(1)
        dup_master = int(m1.group(2))
        dup_scraped = int(m1.group(3))
        new_saved = m1.group(4)
        total_dup = dup_master + dup_scraped
        return f"🧬 会話判定: 受信 {total}、重複廃棄 {total_dup}、新規保存 {new_saved}。"

    # 2. メディア差分のスマート変換
    m2 = re.search(r'受信アセット\s*(\d+)\s*件中、.*重複排除により\s*(\d+)\s*件.*新しく保存したファイルは\s*【(\d+)\s*件】.*現在の物理ファイル総数:\s*(\d+)\s*件', msg)
    if m2:
        received = m2.group(1)
        discarded = m2.group(2)
        saved = m2.group(3)
        total = m2.group(4)
        return f"🧬 メディア判定: 受信 {received}、重複廃棄 {discarded}、新規保存 {saved}、最終ファイル {total}。"

    # 3. リアルタイム同期時のメディア保存変換
    m3 = re.search(r'リアルタイム新規メディアを\s*【(\d+)\s*件】.*現在の物理ファイル総数:\s*(\d+)\s*件', msg)
    if m3:
        saved = m3.group(1)
        total = m3.group(2)
        return f"🧬 メディア同期: 新規保存 {saved}、最終ファイル {total}。"

    # 🌟 修正ポイント: 新規作成のマイルストーンは簡易表示でも消去せず綺麗に整形して残します
    if "[フォルダ新規作成]" in msg:
        m_fold = re.search(r'新しいチャットフォルダ『(.*?)』を作成しました。', msg)
        folder_name = m_fold.group(1) if m_fold else "不明"
        return f"🆕 [新規作成] チャットフォルダ『{folder_name}』を生成しました。"
        
    if "[ファイル新規作成]" in msg:
        return "🆕 [新規作成] 新規の同期ログファイル（raw_scraped.md）を生成しました。"

    # 余分なシステム内部スキャンログのみ簡易モードでクレンジング
    if "基準データ" in msg or "一時退避します" in msg:
        return None

    return msg

# ================= 🌐 連携用のローカルHTTPサーバー =================
class LogHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global server_suspended
        if server_suspended:
            self.send_response(503)
            self.end_headers()
            return

        if self.path == '/log':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                self.server.app.save_received_log_from_thread(data)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.server.app.log_message_from_thread(f"❌ 処理エラー: {e}")
                
        elif self.path == '/cleat_log':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                msg = data.get("message", "")
                self.server.app.log_cleat_message_from_thread(msg)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            except:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/show':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            self.server.app.show_window_from_thread()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS, GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    # 中継通信ログの出力
    def log_message(self, format, *args):
        request_str = args[0]
        status_code = args[1]
        
        # 簡易ログの場合、POST /log 以外の事前確認通信(OPTIONS)などを非表示にして無駄を省きます
        detailed = self.server.app.var_detailed_server.get()
        if not detailed:
            if "POST /log" not in request_str:
                return 
                
        msg = f"📡 接続受入: {request_str} - Status: {status_code}"
        self.server.app.log_message_from_thread(msg)

# ================= 🖥️ スリムサーバー UI =================
class AiReLinkerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("📡 AiReLinker Server (常駐中)")
        self.root.geometry("850x450") 
        self.root.resizable(True, True) 
        
        # 🌟 先に変数を安全に初期化（TclErrorクラッシュの根本防止）
        self.var_detailed_server = tk.BooleanVar(value=True)
        self.var_detailed_cleat = tk.BooleanVar(value=True)
        self.load_log_modes()

        # 🌟 ログの履歴（表示切替時に一瞬で古いログを書き直すためのメモリ領域）
        self.server_log_history = []
        self.cleat_log_history = []

        self.apply_window_icon()
        
        ttk.Style().theme_use('vista')
        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        top_f = ttk.Frame(main_frame)
        top_f.pack(fill="x", side="top", pady=2)
        
        # 起動ボタンエリア（左右2分割）
        launch_btn_f = ttk.Frame(top_f)
        launch_btn_f.pack(fill="x", pady=2)
        
        self.btn_launch_anchor = ttk.Button(launch_btn_f, text="⚓ AiReAnchorメインを起動する", command=self.launch_main_app)
        self.btn_launch_anchor.pack(side="left", expand=True, fill="x", padx=(0, 2))
        
        self.btn_launch_cleat = ttk.Button(launch_btn_f, text="🔨 AiReCleat調停ツールを起動する", command=self.launch_cleat_app)
        self.btn_launch_cleat.pack(side="right", expand=True, fill="x")

        # コントロールボタン列（均等4等分グリッド配置）
        ctrl_f = ttk.Frame(top_f)
        ctrl_f.pack(fill="x", pady=2)
        
        ctrl_f.columnconfigure(0, weight=1, uniform="group")
        ctrl_f.columnconfigure(1, weight=1, uniform="group")
        ctrl_f.columnconfigure(2, weight=1, uniform="group")
        ctrl_f.columnconfigure(3, weight=1, uniform="group")
        
        self.btn_suspend = ttk.Button(ctrl_f, text="⏸ 一時停止", command=self.toggle_suspension)
        self.btn_suspend.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        
        self.btn_shutdown = ttk.Button(ctrl_f, text="⏹ 完全停止", command=self.confirm_exit_app)
        self.btn_shutdown.grid(row=0, column=1, sticky="ew", padx=(0, 2))
        
        self.btn_hide = ttk.Button(ctrl_f, text="📥 トレイに格納", command=self.hide_window)
        self.btn_hide.grid(row=0, column=2, sticky="ew", padx=(0, 2))
        
        self.btn_config = ttk.Button(ctrl_f, text="⚙ 設定", command=self.open_settings_window)
        self.btn_config.grid(row=0, column=3, sticky="ew")

        # 左右並列（水平分割仕様）のログフレーム（極太スライダーバー搭載）
        log_frame = ttk.LabelFrame(main_frame, text=" 📝 サーバー・調停ログコンソール ", padding=8)
        log_frame.pack(fill="both", expand=True, pady=5)
        
        self.pane = tk.PanedWindow(log_frame, orient=tk.HORIZONTAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
        self.pane.pack(fill="both", expand=True)
        
        # 1. サーバー中継ログ（左ペイン）
        self.server_text_frame = ttk.Frame(self.pane)
        self.pane.add(self.server_text_frame, stretch="always") # stretch="always"に固定
        
        # 🌟 【水平スライド連動ヘッダー】左ペインにタイトルと「詳細ログを表示」チェックをパッキング
        left_header_f = ttk.Frame(self.server_text_frame)
        left_header_f.pack(fill="x", side="top", pady=(0, 2))
        lbl_server = ttk.Label(left_header_f, text="📝 AiReLinkerログ", font=("MS Gothic", 9, "bold"))
        lbl_server.pack(side="left", padx=5)
        self.chk_detailed_server = ttk.Checkbutton(left_header_f, text="詳細ログを表示", variable=self.var_detailed_server, command=self.refresh_server_logs)
        self.chk_detailed_server.pack(side="right", padx=5)
        
        left_content_f = ttk.Frame(self.server_text_frame)
        left_content_f.pack(fill="both", expand=True, side="top")
        self.log_text = tk.Text(left_content_f, background="#1e1e1e", fg="#d4d4d4", font=("MS Gothic", 9))
        self.log_text.pack(fill="both", expand=True, side="left")
        sb1 = ttk.Scrollbar(left_content_f, command=self.log_text.yview)
        sb1.pack(fill="y", side="right")
        self.log_text.config(yscrollcommand=sb1.set)
        
        # 2. AiReCleat調停ログ（右ペイン）
        self.cleat_text_frame = ttk.Frame(self.pane)
        
        # 🌟 【水平スライド連動ヘッダー】右ペインにタイトルと「詳細ログを表示」チェックをパッキング
        right_header_f = ttk.Frame(self.cleat_text_frame)
        right_header_f.pack(fill="x", side="top", pady=(0, 2))
        lbl_cleat = ttk.Label(right_header_f, text="📝 AiReCleatログ", font=("MS Gothic", 9, "bold"))
        lbl_cleat.pack(side="left", padx=5)
        self.chk_detailed_cleat = ttk.Checkbutton(right_header_f, text="詳細ログを表示", variable=self.var_detailed_cleat, command=self.refresh_cleat_logs)
        self.chk_detailed_cleat.pack(side="right", padx=5)
        
        right_content_f = ttk.Frame(self.cleat_text_frame)
        right_content_f.pack(fill="both", expand=True, side="top")
        self.cleat_text = tk.Text(right_content_f, background="#1e1e1e", fg="#a0db86", font=("MS Gothic", 9))
        self.cleat_text.pack(fill="both", expand=True, side="left")
        sb2 = ttk.Scrollbar(right_content_f, command=self.cleat_text.yview)
        sb2.pack(fill="y", side="right")
        self.cleat_text.config(yscrollcommand=sb2.set)
        
        self.update_cleat_pane_visibility()

        self.log("🚀 AiReLinker 受信中継サーバーが起動しました。")
        self.start_server_thread()

        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)
        
        self.tray_icon = None
        if HAS_SYSTRAY:
            threading.Thread(target=self.init_systray, daemon=True).start()

    def load_log_modes(self):
        cfg = load_config_data()
        self.var_detailed_server.set(cfg.get("detailed_server", True))
        self.var_detailed_cleat.set(cfg.get("detailed_cleat", True))

    def on_log_mode_changed(self):
        cfg = load_config_data()
        cfg["detailed_server"] = self.var_detailed_server.get()
        cfg["detailed_cleat"] = self.var_detailed_cleat.get()
        save_config_data(cfg)

    # 🌟 【中継ログの動的リアルタイム書き換えリフレッシュ】
    def refresh_server_logs(self):
        self.on_log_mode_changed()
        detailed = self.var_detailed_server.get()
        
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        for msg in self.server_log_history:
            if not detailed:
                # 簡易ログの場合、POST /log 以外の細かな通信記述を画面から非表示にします
                if "POST /log" not in msg and "Pythonサーバー" not in msg and "起動しました" not in msg:
                    continue
            self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    # 🌟 【調停ログの動的リアルタイム書き換えリフレッシュ】
    def refresh_cleat_logs(self):
        self.on_log_mode_changed()
        detailed = self.var_detailed_cleat.get()
        
        self.cleat_text.config(state="normal")
        self.cleat_text.delete("1.0", tk.END)
        for msg in self.cleat_log_history:
            if not detailed:
                simplified = simplify_cleat_message(msg)
                if not simplified:
                    continue
                self.cleat_text.insert(tk.END, simplified + "\n")
            else:
                self.cleat_text.insert(tk.END, msg + "\n")
        self.cleat_text.see(tk.END)
        self.cleat_text.config(state="disabled")

    def update_cleat_pane_visibility(self):
        cfg = load_config_data()
        show_cleat = cfg.get("show_cleat_logs", True)
        
        try:
            panes = self.pane.panes()
            is_added = str(self.cleat_text_frame) in [str(p) for p in panes]
        except:
            is_added = False

        if show_cleat:
            if not is_added:
                self.pane.add(self.cleat_text_frame, stretch="always")
        else:
            if is_added:
                self.pane.forget(self.cleat_text_frame)

    def apply_window_icon(self):
        if os.path.exists(ICON_SERVER):
            try:
                self.root.iconbitmap(default=ICON_SERVER)
                img = Image.open(ICON_SERVER)
                self._icon_photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self._icon_photo)
            except:
                try:
                    self.root.iconbitmap(ICON_SERVER)
                except: pass

    def log(self, message):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        msg = f"[{now}] {message}"
        self.server_log_history.append(msg) # メモリに履歴をストック
        self.refresh_server_logs() # 最新の状態にフィルタリング再描画

    def log_cleat_message(self, message):
        self.cleat_log_history.append(message) # メモリに履歴をストック
        self.refresh_cleat_logs() # 最新の状態にフィルタリング再描画

    def log_message_from_thread(self, message):
        self.root.after(0, lambda: self.log(message))

    def log_cleat_message_from_thread(self, message):
        self.root.after(0, lambda: self.log_cleat_message(message))

    def show_window_from_thread(self):
        self.root.after(0, self.show_window_and_focus)

    def show_window_and_focus(self):
        self.show_window()
        self.root.focus_force()
        self.log("🔔 二重起動を検知したため、既存のウィンドウを前面に呼び出しました。")

    def start_server_thread(self):
        def run_server():
            try:
                self.server_inst = HTTPServer(('', PORT), LogHTTPRequestHandler)
                self.server_inst.app = self
                self.log_message_from_thread(f"📡 Pythonサーバーが稼働中 (ポート: {PORT})")
                self.server_inst.serve_forever()
            except Exception as e:
                self.log_message_from_thread(f"❌ サーバー起動失敗: {e}")
        threading.Thread(target=run_server, daemon=True).start()

    def toggle_suspension(self):
        global server_suspended
        server_suspended = not server_suspended
        if server_suspended:
            self.btn_suspend.config(text="▶ サーバー再開")
            self.log("⏸ サーバーを一時停止しました（受信データは破棄されます）。")
        else:
            self.btn_suspend.config(text="⏸ 一時停止")
            self.log("▶ サーバーを再開しました（ログの保存を再開します）。")
        
        if self.tray_icon:
            self.update_tray_menu()

    def confirm_exit_app(self):
        if messagebox.askyesno("完全停止の確認", "AiReLinker常駐サーバーを完全に終了しますか？"):
            self.exit_app()

    def open_settings_window(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("⚙ AiReLinkerサーバー詳細設定")
        settings_win.geometry("380x240")
        settings_win.resizable(False, False)
        settings_win.grab_set()

        if hasattr(self, '_icon_photo'):
            settings_win.iconphoto(False, self._icon_photo)

        frame = ttk.Frame(settings_win, padding=15)
        frame.pack(fill="both", expand=True)

        cfg = load_config_data()
        
        var_start_hidden = tk.BooleanVar(value=cfg.get("start_hidden", False))
        var_startup = tk.BooleanVar(value=cfg.get("startup", False))
        var_show_cleat = tk.BooleanVar(value=cfg.get("show_cleat_logs", True))

        safe_font = ("MS PGothic", 10, "bold")
        ttk.Label(frame, text="■ 動作オプション設定", font=safe_font).pack(anchor="w", pady=(0, 10))

        chk_hidden = ttk.Checkbutton(frame, text="Windows起動時にウィンドウを開かず、トレイに格納する", variable=var_start_hidden)
        chk_hidden.pack(anchor="w", pady=3)

        chk_startup = ttk.Checkbutton(frame, text="Windowsログイン時にこのサーバーを自動で起動する", variable=var_startup)
        chk_startup.pack(anchor="w", pady=3)

        chk_cleat = ttk.Checkbutton(frame, text="調停マネージャー（AiReCleat）の稼働ログを表示する", variable=var_show_cleat)
        chk_cleat.pack(anchor="w", pady=3)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", side="bottom", pady=(10, 0))

        def save_settings():
            cfg["start_hidden"] = var_start_hidden.get()
            cfg["show_cleat_logs"] = var_show_cleat.get()
            
            old_startup = cfg.get("startup", False)
            new_startup = var_startup.get()
            cfg["startup"] = new_startup
            
            save_config_data(cfg)
            self.update_cleat_pane_visibility()
            
            if old_startup != new_startup:
                self.apply_startup_registry(new_startup)
                
            self.log("⚙ 設定を更新しました。")
            settings_win.destroy()

        ttk.Button(btn_frame, text="適用して保存", command=save_settings).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="キャンセル", command=settings_win.destroy).pack(side="right")

    def apply_startup_registry(self, enable):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "AiReLinkerServer"
        script_path = os.path.abspath(sys.argv[0])
        cmd = f'"{sys.executable}" "{script_path}" --background'

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                self.log("➕ WindowsスタートアップにAiReLinkerServerを登録しました。")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    self.log("➖ Windowsスタートアップから登録を解除しました。")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            self.log_message_from_thread(f"❌ スタートアップレジストリ操作に失敗しました: {e}")
            messagebox.showerror("レジストリエラー", f"スタートアップの設定に失敗しました:\n{e}")

    # 【スレッドセーフな保存フック】
    def save_received_log_from_thread(self, data):
        self.root.after(0, lambda: self.save_received_log(data))

    # ================= 💾 受信ログのローカル一時保存処理 =================
    def save_received_log(self, data):
        # 送信された ai_service 名（例: "AI Overviews"）を最優先でそのままフォルダ名として採用
        explicit_service = data.get("ai_service", "").strip()
        if explicit_service:
            ai_folder_name = explicit_service
        else:
            # 従来のフォールバック判定
            ai_folder_name = "Gemini" if "gemini.google.com" in data.get('url', '').lower() else "Google AI Studio"

        thread_id = sanitize_filename(data.get("chat_title", "Untitled_Chat"))
        chat_folder = os.path.join(SAVE_DIR, ai_folder_name, thread_id)
        scraped_folder = os.path.join(chat_folder, "scraped")
        os.makedirs(scraped_folder, exist_ok=True)
        
        # 【超軽量ポストオフィス仕様】
        payload_path = os.path.join(scraped_folder, "raw_payload.json")
        try:
            with open(payload_path, "w", encoding="utf-8") as pf:
                json.dump(data, pf, indent=4, ensure_ascii=False)
            
            # 【非表示キック】
            pythonw_exe = sys.executable.replace('python.exe', 'pythonw.exe')
            if os.path.exists(CLEAT_APP_PATH):
                detailed_cleat_val = "1" if self.var_detailed_cleat.get() else "0"
                subprocess.Popen([pythonw_exe, CLEAT_APP_PATH, "--chat-folder", chat_folder, "--sync-mode", data.get("sync_mode", "full"), "--detailed-log", detailed_cleat_val])
            else:
                self.log(f"⚠️ 警告: {CLEAT_APP_PATH} が見つかりません。")
        except Exception as e:
            self.log(f"❌ ペイロードの保存に失敗しました: {e}")

    # 🌟 【アプリの連携起動関数】
    def launch_main_app(self):
        if os.path.exists(MAIN_APP_PATH):
            try:
                if MAIN_APP_PATH.endswith('.pyw'):
                    pythonw_exe = sys.executable.replace('python.exe', 'pythonw.exe')
                    subprocess.Popen([pythonw_exe, MAIN_APP_PATH])
                else:
                    subprocess.Popen([sys.executable, MAIN_APP_PATH])
                self.log("⚓ AiReAnchor Main System を起動しました。")
            except Exception as e:
                messagebox.showerror("エラー", f"メインアプリの起動に失敗しました: {e}")
        else:
            messagebox.showerror("エラー", f"メインアプリが見つかりません:\n{MAIN_APP_PATH}")

    # 🌟 【AiReCleat.pyw の自動呼び出し】
    def launch_cleat_app(self):
        if os.path.exists(CLEAT_APP_PATH):
            try:
                pythonw_exe = sys.executable.replace('python.exe', 'pythonw.exe')
                subprocess.Popen([pythonw_exe, CLEAT_APP_PATH])
                self.log("🔨 AiReCleat Standalone UI を起動しました。")
            except Exception as e:
                messagebox.showerror("エラー", f"調停ツールの起動に失敗しました: {e}")
        else:
            messagebox.showerror("エラー", f"調停ツール(AiReCleat.pyw)が見つかりません:\n{CLEAT_APP_PATH}")

    def init_systray(self):
        if not os.path.exists(ICON_SERVER):
            return
        try:
            self.tray_image = Image.open(ICON_SERVER)
            self.create_tray_icon()
        except Exception as e:
            self.log_message_from_thread(f"⚠️ トレイアイコンの作成に失敗しました: {e}")

    def create_tray_icon(self):
        suspend_label = "▶ サーバーを再開" if server_suspended else "⏸ サーバーを一時停止"
        
        menu = (
            item('⚓ AiReAnchorを起動', self.launch_main_app),
            item(suspend_label, lambda icon, item: self.root.after(0, self.toggle_suspension)),
            item('⚙ 設定を開く', lambda icon, item: self.root.after(0, self.open_settings_window)),
            item('👁️ サーバー画面を表示', lambda icon, item: self.root.after(0, self.show_window)),
            item('❌ サーバーを完全に終了', lambda icon, item: self.root.after(0, self.exit_app))
        )
        
        if self.tray_icon:
            self.tray_icon.stop()

        self.tray_icon = pystray.Icon("AiReLinker", self.tray_image, "AiReLinker Server", menu)
        self.tray_icon.run()

    def update_tray_menu(self):
        if self.tray_icon:
            threading.Thread(target=self.create_tray_icon, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()

    def exit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        sys.exit(0)

if __name__ == '__main__':
    root = tk.Tk()
    app_ui = AiReLinkerUI(root)
    try: root.mainloop()
    except KeyboardInterrupt: pass