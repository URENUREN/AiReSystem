# -*- coding: utf-8 -*-
# AiReAnchorSettingsTab.pyw - 環境設定・統合ホスト (左右マルチカラム最適化 ＆ サーバー起動機能追加版)
import os
import sys
import json
import re
import urllib.request
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico")

# 🌟 AiReAccessway (APIタブ統合版) のドッキング
try:
    from AiReAccessway import AiReAccesswayFrame
    HAS_ACCESSWAY_MODULE = True
except ImportError:
    HAS_ACCESSWAY_MODULE = False

# デフォルトのサービスマッピングテーブル
DEFAULT_SERVICE_MAPPINGS = [
    {
        "canonical_name": "Google AI Studio",
        "keywords": ["aistudio.google.com", "google ai studio", "aistudio", "ai studio"]
    },
    {
        "canonical_name": "Gemini",
        "keywords": ["gemini.google.com", "gemini"]
    },
    {
        "canonical_name": "ChatGPT",
        "keywords": ["chatgpt.com", "chat.openai.com", "chatgpt", "openai"]
    },
    {
        "canonical_name": "Claude",
        "keywords": ["claude.ai", "claude", "anthropic"]
    },
    {
        "canonical_name": "Perplexity",
        "keywords": ["perplexity.ai", "perplexity"]
    },
    {
        "canonical_name": "NotebookLM",
        "keywords": ["notebooklm.google.com", "notebooklm"]
    },
    {
        "canonical_name": "Local LLM",
        "keywords": ["localhost", "127.0.0.1", "ollama", "lmstudio", "local_llm"]
    }
]


def normalize_service_name(input_str_or_url, config=None):
    """
    🌟 システム共通判定関数: URLや入力文字列から正式なサービスフォルダ名を動的に返却
    """
    if not input_str_or_url:
        return "その他AIサービス"

    if config is None:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: config = json.load(f)
            except: config = {}
        else: config = {}

    mappings = config.get("service_mappings", DEFAULT_SERVICE_MAPPINGS)
    lower_input = str(input_str_or_url).lower().strip()

    for item in mappings:
        canonical = item.get("canonical_name", "その他AIサービス")
        keywords = item.get("keywords", [])
        for kw in keywords:
            if kw.lower() in lower_input:
                return canonical

    clean_name = re.sub(r'[\\/*?:"<>|]', "_", str(input_str_or_url)).strip()
    return clean_name if clean_name else "その他AIサービス"


# Windows特有のAppID登録
try:
    import ctypes
    myappid = 'airelinker.suite.settings.v3'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


class AiReAnchorSettingsFrame(ttk.Frame):
    """🌟 システム全般の設定を集約・管理するメインGUIホストフレーム (左右マルチカラム版)"""
    def __init__(self, parent, main_app=None):
        super().__init__(parent)
        self.main_app = main_app
        
        if self.main_app:
            self.config = self.main_app.config
            self.save_dir = self.main_app.save_dir
            self.ai_colors = getattr(self.main_app, 'ai_colors', {})
        else:
            self.config = self.load_config()
            self.save_dir = self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))
            self.ai_colors = self.config.get("ai_colors", {})

        # 初期値チェック
        if "service_mappings" not in self.config:
            self.config["service_mappings"] = DEFAULT_SERVICE_MAPPINGS
            self.save_config()

        self.build_widgets()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            if self.main_app:
                self.main_app.config = self.config
                self.main_app.save_dir = self.save_dir
        except Exception as e:
            messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")

    def build_widgets(self):
        # スクロール可能なメインキャンバス
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # =========================================================================
        # 🌟 上段コンテナ（左右2カラム構成）
        # =========================================================================
        top_container = ttk.Frame(self.scrollable_frame, padding=(10, 5))
        top_container.pack(fill="x", side="top")
        
        top_container.columnconfigure(0, weight=1) # 左カラム
        top_container.columnconfigure(1, weight=1) # 右カラム

        left_column = ttk.Frame(top_container)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        right_column = ttk.Frame(top_container)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # -------------------------------------------------------------------------
        # 1. 【左カラム上】 🎨 カラーテーマ ＆ デザインスタイル設定
        # -------------------------------------------------------------------------
        theme_f = ttk.LabelFrame(left_column, text=" 🎨 カラーテーマ ＆ デザインスタイル設定 ", padding=8)
        theme_f.pack(fill="x", pady=(0, 6))

        ttk.Label(
            theme_f, 
            text="💡 メイン画面のビジュアル・背景トーンを選択できます。", 
            font=("MS Gothic", 8)
        ).pack(anchor="w", pady=(0, 4))

        current_mode = self.config.get("theme_mode", "classic_retro")
        self.theme_var = tk.StringVar(value=current_mode)

        rb_retro = ttk.Radiobutton(
            theme_f, 
            text="📻 クラシック・レトロオード色調", 
            value="classic_retro", 
            variable=self.theme_var, 
            command=self.on_theme_changed
        )
        rb_retro.pack(anchor="w", pady=2, padx=5)

        rb_modern = ttk.Radiobutton(
            theme_f, 
            text="📻 モダン・ライトスタイル", 
            value="modern_light", 
            variable=self.theme_var, 
            command=self.on_theme_changed
        )
        rb_modern.pack(anchor="w", pady=2, padx=5)

        # -------------------------------------------------------------------------
        # 2. 【左カラム中】 📡 AiReLinker 中継サーバー起動・管理 (★新規追加)
        # -------------------------------------------------------------------------
        server_f = ttk.LabelFrame(left_column, text=" 📡 AiReLinker 中継サーバー (ポート 5000) ", padding=8)
        server_f.pack(fill="x", pady=(0, 6))

        ttk.Label(
            server_f,
            text="💡 ブラウザ拡張からの対話ログを受信・中継する常駐サーバーです。",
            font=("MS Gothic", 8)
        ).pack(anchor="w", pady=(0, 4))

        btn_server = ttk.Button(
            server_f,
            text="🚀 AiReLinker サーバーを起動する / 前面表示",
            command=self.launch_linker_server
        )
        btn_server.pack(fill="x", pady=2)

        # -------------------------------------------------------------------------
        # 3. 【左カラム下】 📁 ログデータの保存場所設定
        # -------------------------------------------------------------------------
        path_f = ttk.LabelFrame(left_column, text=" 📁 ログデータの保存場所設定 ", padding=8)
        path_f.pack(fill="x", pady=(0, 0))
        
        self.save_dir_var = tk.StringVar(value=self.save_dir)
        
        path_entry_f = ttk.Frame(path_f)
        path_entry_f.pack(fill="x", pady=2)
        ttk.Entry(path_entry_f, textvariable=self.save_dir_var, state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(path_entry_f, text="📂 参照...", command=self.change_save_directory).pack(side="right")

        # -------------------------------------------------------------------------
        # 4. 【右カラム】 🏷️ AIサービス表記ゆれ ＆ 自動フォルダ名マッピング管理
        # -------------------------------------------------------------------------
        map_f = ttk.LabelFrame(right_column, text=" 🏷️ AIサービス表記ゆれ ＆ 自動フォルダ名マッピング管理 ", padding=8)
        map_f.pack(fill="both", expand=True)

        ttk.Label(
            map_f, 
            text="💡 URLやキーワードを元に、保存先の「正式フォルダ名」を定義します。", 
            font=("MS Gothic", 8)
        ).pack(anchor="w", pady=(0, 2))

        # 一覧ツリー表示（コンパクトな高さに調整）
        tree_f = ttk.Frame(map_f)
        tree_f.pack(fill="both", expand=True, pady=2)

        self.tree_map = ttk.Treeview(tree_f, columns=("Canonical", "Keywords"), show="headings", height=4)
        self.tree_map.heading("Canonical", text="正式フォルダ名")
        self.tree_map.heading("Keywords", text="識別キーワード / ドメイン (カンマ区切り)")
        self.tree_map.column("Canonical", width=120, anchor="w")
        self.tree_map.column("Keywords", width=260, anchor="w")
        self.tree_map.pack(side="left", fill="both", expand=True)

        sb_m = ttk.Scrollbar(tree_f, command=self.tree_map.yview)
        sb_m.pack(side="right", fill="y")
        self.tree_map.configure(yscrollcommand=sb_m.set)

        # 新規追加・編集コントロール
        edit_f = ttk.Frame(map_f)
        edit_f.pack(fill="x", pady=2)

        ttk.Label(edit_f, text="正式:").pack(side="left")
        self.entry_canonical = ttk.Entry(edit_f, width=12)
        self.entry_canonical.pack(side="left", padx=2)

        ttk.Label(edit_f, text="KW/URL:").pack(side="left", padx=(4, 0))
        self.entry_keywords = ttk.Entry(edit_f, width=18)
        self.entry_keywords.pack(side="left", padx=2)

        btn_add = ttk.Button(edit_f, text="➕ 追加", command=self.add_mapping_rule)
        btn_add.pack(side="left", padx=2)

        btn_del = ttk.Button(edit_f, text="🗑️ 削除", command=self.delete_selected_mapping)
        btn_del.pack(side="left", padx=2)

        btn_save_m = ttk.Button(map_f, text="💾 マッピングルールを保存", command=self.save_mappings_to_config)
        btn_save_m.pack(anchor="e", pady=(2, 0))

        self.load_mappings_to_tree()

        # =========================================================================
        # 5. 【下段】 🧠 AI実行ハブ ＆ API接続設定 (AiReAccessway)
        # =========================================================================
        if HAS_ACCESSWAY_MODULE:
            self.accessway_frame = AiReAccesswayFrame(self.scrollable_frame, self.config, self.save_config)
            self.accessway_frame.pack(fill="x", pady=5, padx=10)
        else:
            err_f = ttk.LabelFrame(self.scrollable_frame, text=" 🧠 AI実行ハブ (AiReAccessway) ")
            err_f.pack(fill="x", pady=5, padx=10)
            ttk.Label(err_f, text="⚠️ AiReAccessway.pyw が見つからないかエラーのため読み込めません。").pack(pady=10)

    def launch_linker_server(self):
        """🌟 AiReLinker 中継サーバーの起動 / 前面化"""
        try:
            req = urllib.request.urlopen("http://127.0.0.1:5000/show", timeout=1)
            messagebox.showinfo("サーバー状態", "AiReLinker サーバーはすでに稼働中です。\n画面を前面に表示しました。")
        except Exception:
            server_path_pyw = os.path.normpath(os.path.join(CURRENT_DIR, "AiReLinkerServer.pyw"))
            server_path_py = os.path.normpath(os.path.join(CURRENT_DIR, "AiReLinkerServer.py"))
            
            target_path = server_path_pyw if os.path.exists(server_path_pyw) else (server_path_py if os.path.exists(server_path_py) else None)
            
            if target_path:
                try:
                    pythonw_exe = sys.executable.replace('python.exe', 'pythonw.exe')
                    if not os.path.exists(pythonw_exe):
                        pythonw_exe = sys.executable
                    subprocess.Popen([pythonw_exe, target_path])
                    messagebox.showinfo("起動成功", f"AiReLinker サーバーを起動しました。\n({os.path.basename(target_path)})")
                except Exception as e:
                    messagebox.showerror("エラー", f"サーバー起動に失敗しました:\n{e}")
            else:
                messagebox.showerror("エラー", "AiReLinkerServer.pyw (または .py) が見つかりませんでした。")

    def on_theme_changed(self):
        """🌟 ラジオボタン切替時にその場でテーマを即時適用・保存"""
        new_mode = self.theme_var.get()
        self.config["theme_mode"] = new_mode
        self.save_config()

        if self.main_app and hasattr(self.main_app, "apply_theme_style"):
            self.main_app.apply_theme_style(new_mode)

    # --- マッピング管理のGUI制御メソッド群 ---
    def load_mappings_to_tree(self):
        self.tree_map.delete(*self.tree_map.get_children())
        mappings = self.config.get("service_mappings", DEFAULT_SERVICE_MAPPINGS)
        for idx, item in enumerate(mappings):
            c_name = item.get("canonical_name", "")
            k_list = ", ".join(item.get("keywords", []))
            self.tree_map.insert("", "end", iid=str(idx), values=(c_name, k_list))

    def add_mapping_rule(self):
        c_name = self.entry_canonical.get().strip()
        k_str = self.entry_keywords.get().strip()

        if not c_name or not k_str:
            messagebox.showwarning("警告", "「正式名」と「キーワード」の両方を入力してください。")
            return

        keywords = [k.strip() for k in k_str.split(",") if k.strip()]
        
        mappings = self.config.setdefault("service_mappings", [])
        mappings.append({"canonical_name": c_name, "keywords": keywords})

        self.entry_canonical.delete(0, tk.END)
        self.entry_keywords.delete(0, tk.END)
        self.load_mappings_to_tree()

    def delete_selected_mapping(self):
        sel = self.tree_map.selection()
        if not sel:
            messagebox.showwarning("警告", "削除するマッピングルールをリストから選択してください。")
            return

        idx = int(sel[0])
        mappings = self.config.get("service_mappings", [])
        if 0 <= idx < len(mappings):
            del mappings[idx]
            self.load_mappings_to_tree()

    def save_mappings_to_config(self):
        self.save_config()
        messagebox.showinfo("成功", "AIサービスのマッピング定義を config.json に保存しました！")

    def change_save_directory(self):
        new_dir = filedialog.askdirectory(title="ログデータの保存先フォルダを選択してください", initialdir=self.save_dir)
        if new_dir:
            new_dir = os.path.normpath(new_dir)
            self.save_dir = new_dir
            self.save_dir_var.set(new_dir)
            self.config["save_dir"] = new_dir
            self.save_config()
            if self.main_app and hasattr(self.main_app, 'refresh_portal_data'):
                self.main_app.refresh_portal_data()
            messagebox.showinfo("成功", f"ログの保存先フォルダを変更しました:\n{new_dir}")

    def force_fit_canvas(self):
        try:
            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            if canvas_width > 10:
                self.canvas.itemconfig(self.canvas_window, width=canvas_width)
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception as e:
            if self.main_app:
                sys.excepthook(type(e), e, e.__traceback__)


# ================= 🖥️ 単体起動時のテストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("⚙️ AiReAnchorSettingsTab テスト")
    root.geometry("900x700")

    if os.path.exists(ICON_PORTAL):
        try: root.iconbitmap(ICON_PORTAL)
        except: pass

    settings_frame = AiReAnchorSettingsFrame(root)
    settings_frame.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()