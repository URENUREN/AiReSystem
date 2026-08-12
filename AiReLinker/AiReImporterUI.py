# -*- coding: utf-8 -*-
# AiReImporterUI.py - インポーター超軽量GUIレイアウト・ウィジェット構築モジュール (完全版)
import os
import sys
import json
import datetime
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 分割したダイアログ ＆ 実行ロジックのインポート
from AiReImporterDialogs import (
    show_chat_preview_dialog,
    show_report_popout_window,
    show_single_chat_detail_report,
    show_all_files_report,
    show_detected_chats_report,
    show_linked_assets_report,
    show_missing_assets_report,
    show_duplicate_assets_report,
    show_missing_links_report,
    show_help_dialog,
    confirm_app_close,
    render_chat_markdown,
    render_clean_report_markdown
)
from AiReImporterLogic import (
    run_scan_process,
    run_deep_analysis_process,
    run_import_process,
    run_compact_other_dir_process,
    run_manual_assets_compact_process
)

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CURRENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_IMPORTER = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReLinkerImporter.ico"))
ICON_FALLBACK = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")

def load_config():
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

class AiReLinkerImporterFrame(ttk.Frame):
    """メインGUIコンポーネントクラス（超軽量レイアウト・イベント仲介）"""
    def __init__(self, parent, main_app=None):
        super().__init__(parent)
        self.main_app = main_app

        if self.main_app:
            self.config = self.main_app.config
            self.save_dir = self.main_app.save_dir
        else:
            self.config = load_config()
            self.save_dir = self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))

        self.scanned_chats_data = []
        self.manual_compact_targets = []
        self.last_linked_assets = set()
        self.last_missing_assets = []
        self.last_duplicate_map = {}
        self.last_missing_links = []
        self.is_analyzed = False
        self.current_view_state = "chat" # "chat" or "report"
        self.current_report_type = ""
        self.last_rendered_report_md = ""
        self.last_rendered_chat_md = ""
        self.last_normal_geometry = "950x680"

        self._icon_photo = None
        self.init_icon_photo()

        self.build_ui()
        self.after(100, self.setup_window_close_hook)

    def init_icon_photo(self):
        icon_path = ICON_IMPORTER if os.path.exists(ICON_IMPORTER) else ICON_FALLBACK
        if os.path.exists(icon_path):
            try:
                if HAS_PIL:
                    img = Image.open(icon_path)
                    self._icon_photo = ImageTk.PhotoImage(img)
                else:
                    self._icon_photo = tk.PhotoImage(file=icon_path)
            except: pass

    def apply_window_icon(self, window):
        if not window: return
        icon_path = ICON_IMPORTER if os.path.exists(ICON_IMPORTER) else ICON_FALLBACK
        if os.path.exists(icon_path):
            try: window.iconbitmap(icon_path)
            except: pass
        if self._icon_photo:
            try: window.iconphoto(True, self._icon_photo)
            except: pass

    def build_ui(self):
        cfg = load_config()

        # 1. 最上部コントロールバー
        layout_bar = ttk.Frame(self)
        layout_bar.pack(fill="x", side="top", pady=2)

        ttk.Label(layout_bar, text="🖥️ 画面レイアウト:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.layout_mode_var = tk.StringVar(value=cfg.get("importer_layout_mode", "vertical"))
        ttk.Radiobutton(layout_bar, text="縦型スリム表示", variable=self.layout_mode_var, value="vertical", command=self.rebuild_layout).pack(side="left", padx=5)
        ttk.Radiobutton(layout_bar, text="横型2分割表示", variable=self.layout_mode_var, value="horizontal_2", command=self.rebuild_layout).pack(side="left", padx=5)
        ttk.Radiobutton(layout_bar, text="横型3分割表示", variable=self.layout_mode_var, value="horizontal_3", command=self.rebuild_layout).pack(side="left", padx=5)

        ttk.Label(layout_bar, text=" | ⇄ 配置:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.pane_side_var = tk.StringVar(value=cfg.get("importer_pane_side", "right"))
        ttk.Radiobutton(layout_bar, text="標準(右)", variable=self.pane_side_var, value="right", command=self.rebuild_layout).pack(side="left", padx=3)
        ttk.Radiobutton(layout_bar, text="反転(左)", variable=self.pane_side_var, value="left", command=self.rebuild_layout).pack(side="left", padx=3)

        ttk.Label(layout_bar, text=" | ⚙️ インポート処理:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.run_mode_var = tk.StringVar(value="auto")
        ttk.Radiobutton(layout_bar, text="順次全自動", variable=self.run_mode_var, value="auto", command=self.toggle_run_mode).pack(side="left", padx=5)
        ttk.Radiobutton(layout_bar, text="ステップ実行 (段階調停)", variable=self.run_mode_var, value="step", command=self.toggle_run_mode).pack(side="left", padx=5)

        ttk.Label(layout_bar, text=" | 👁️ パネル:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.var_show_preview = tk.BooleanVar(value=cfg.get("importer_show_preview", True))
        self.var_show_log = tk.BooleanVar(value=cfg.get("importer_show_log", True))
        ttk.Checkbutton(layout_bar, text="プレビュー", variable=self.var_show_preview, command=self.rebuild_layout).pack(side="left", padx=3)
        ttk.Checkbutton(layout_bar, text="ログ", variable=self.var_show_log, command=self.rebuild_layout).pack(side="left", padx=3)

        ttk.Button(layout_bar, text="❓ ヘルプ", command=lambda: show_help_dialog(self, self.apply_window_icon)).pack(side="right", padx=5)
        ttk.Button(layout_bar, text="🚪 終了", command=self.on_app_close).pack(side="right", padx=5)

        # メインコンテナ
        self.main_container = ttk.Frame(self)
        self.main_container.pack(fill="both", expand=True, padx=5, pady=5)

        # コンポーネント実体
        self.settings_frame = ttk.Frame(self)
        self.tree_frame = ttk.LabelFrame(self, text=" 📝 検出されたチャット一覧（ダブルクリックでプレビュー先読み） ")
        self.log_frame = ttk.LabelFrame(self, text=" 📝 アセット最適化 ＆ 調停ログ ")
        self.preview_frame = ttk.LabelFrame(self, text=" 📖 マークダウンプレビュー表示 ")

        # PanedWindow 変数
        self.pane = None
        self.left_pane = None
        self.right_pane = None

        # 設定コントロールフレーム内部構築
        svc_f = ttk.Frame(self.settings_frame)
        svc_f.pack(fill="x", pady=2)
        ttk.Label(svc_f, text="🤖 AIサービス指定:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.service_var = tk.StringVar(value="自動判別")
        self.combo_svc = ttk.Combobox(svc_f, textvariable=self.service_var, values=["自動判別", "Google AI Studio", "Gemini", "AI Overviews", "ChatGPT", "Claude", "NotebookLM", "Genspark", "Perplexity", "Local LLM", "新規追加..."], state="readonly", width=15)
        self.combo_svc.pack(side="left", padx=5)
        self.combo_svc.bind("<<ComboboxSelected>>", self.on_combo_select)

        self.new_svc_frame = ttk.Frame(svc_f)
        ttk.Label(self.new_svc_frame, text="手動フォルダ名:").pack(side="left", padx=5)
        self.new_svc_entry = ttk.Entry(self.new_svc_frame, width=15)
        self.new_svc_entry.pack(side="left")

        ttk.Label(svc_f, text=" | 解析モード:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=10)
        self.parse_mode_var = tk.StringVar(value="すべてのファイル")
        self.combo_parse = ttk.Combobox(svc_f, textvariable=self.parse_mode_var, values=["すべてのファイル", "拡張子なしファイルのみ", "JSONファイルのみ (.json)", "Markdownファイルのみ (.md)"], state="readonly", width=22)
        self.combo_parse.pack(side="left", padx=5)

        self.var_import_body = tk.BooleanVar(value=True)
        self.var_import_media = tk.BooleanVar(value=True)
        ttk.Checkbutton(svc_f, text="本文を取り込む", variable=self.var_import_body).pack(side="left", padx=10)
        ttk.Checkbutton(svc_f, text="アセット復元", variable=self.var_import_media).pack(side="left", padx=10)

        path_f = ttk.Frame(self.settings_frame)
        path_f.pack(fill="x", pady=2)
        ttk.Label(path_f, text="インポート元フォルダ:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.src_dir_var = tk.StringVar()
        ttk.Entry(path_f, textvariable=self.src_dir_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(path_f, text="参照...", command=self.select_source_dir).pack(side="left", padx=2)

        # アクションボタン群
        btn_action_f = ttk.Frame(self.settings_frame)
        btn_action_f.pack(fill="x", pady=4)
        self.btn_scan = ttk.Button(btn_action_f, text="🔍 スキャン開始", command=lambda: run_scan_process(self))
        self.btn_scan.pack(side="left", padx=3)
        self.btn_deep_analyze = ttk.Button(btn_action_f, text="🧬 アセット詳細解析", command=lambda: run_deep_analysis_process(self), state="disabled")
        self.btn_deep_analyze.pack(side="left", padx=3)
        self.btn_run_import = ttk.Button(btn_action_f, text="🔨 インポート調停実行", command=lambda: run_import_process(self), state="disabled")
        self.btn_run_import.pack(side="left", padx=3)
        self.btn_compact_assets = ttk.Button(btn_action_f, text="🔨 アセット最適化を実行", command=lambda: run_manual_assets_compact_process(self), state="disabled")
        self.btn_compact_assets.pack(side="left", padx=3)
        self.btn_import_other = ttk.Button(btn_action_f, text="📁 別フォルダへインポート", command=lambda: run_import_process(self, override_save_dir=filedialog.askdirectory(title="別保存先フォルダの選択")), state="disabled")
        self.btn_import_other.pack(side="left", padx=3)
        self.btn_compact_other = ttk.Button(btn_action_f, text="📁 別フォルダのアセット最適化", command=lambda: run_compact_other_dir_process(self))
        self.btn_compact_other.pack(side="left", padx=3)

        self.drop_lbl = ttk.Label(self.settings_frame, text="👉 ここにエクスポートされたAIチャットのフォルダをドロップしてください", font=("MS Gothic", 9))
        self.drop_lbl.pack(pady=2)

        dest_f = ttk.Frame(self.settings_frame)
        dest_f.pack(fill="x", pady=2)
        ttk.Label(dest_f, text="インポート先（保存先）:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.dest_dir_var = tk.StringVar(value=self.save_dir)
        ttk.Entry(dest_f, textvariable=self.dest_dir_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(dest_f, text="参照...", command=self.select_dest_dir).pack(side="left", padx=2)

        policy_f = ttk.LabelFrame(self.settings_frame, text=" 🧬 重複・上書き競合解決ポリシー ")
        policy_f.pack(fill="x", pady=2, padx=5)
        self.policy_var = tk.StringVar(value="merge")
        ttk.Radiobutton(policy_f, text="完全結合（いいとこ取り自動マージ）", variable=self.policy_var, value="merge").pack(side="left", padx=10)
        ttk.Radiobutton(policy_f, text="既存優先（神聖保護）", variable=self.policy_var, value="preserve").pack(side="left", padx=10)
        ttk.Radiobutton(policy_f, text="新規優先（上書き更新）", variable=self.policy_var, value="overwrite").pack(side="left", padx=10)
        ttk.Radiobutton(policy_f, text="上書きしない（スキップ）", variable=self.policy_var, value="skip").pack(side="left", padx=10)

        triage_option_f = ttk.Frame(self.settings_frame)
        triage_option_f.pack(fill="x", pady=2)
        ttk.Label(triage_option_f, text="元フォルダ処理:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)
        self.policy_src_op = tk.StringVar(value="copy")
        ttk.Radiobutton(triage_option_f, text="コピー（安全推奨）", variable=self.policy_src_op, value="copy").pack(side="left", padx=10)
        ttk.Radiobutton(triage_option_f, text="切り取り（引き算整理）", variable=self.policy_src_op, value="cut").pack(side="left", padx=10)

        ttk.Label(triage_option_f, text=" | 迷子アセット処理:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=10)
        self.policy_stray_op = tk.StringVar(value="leave")
        ttk.Radiobutton(triage_option_f, text="元の場所に残す", variable=self.policy_stray_op, value="leave").pack(side="left", padx=10)
        ttk.Radiobutton(triage_option_f, text="救出（サルベージ）", variable=self.policy_stray_op, value="salvage").pack(side="left", padx=10)

        # 6大指標診断ボード
        self.board_lf = ttk.LabelFrame(self.settings_frame, text=" 📊 フォルダデータ診断ボード ")
        self.board_lf.pack(fill="x", pady=4, padx=5)

        self.lbl_stat_total = ttk.Label(self.board_lf, text="📂 総ファイル数: 待機中...", font=("MS Gothic", 9, "bold"), foreground="#2980b9", cursor="hand2")
        self.lbl_stat_total.pack(side="left", padx=6, expand=True)
        self.lbl_stat_total.bind("<Button-1>", lambda e: show_all_files_report(self))

        self.lbl_stat_chats = ttk.Label(self.board_lf, text="💬 検出チャット: 待機中...", font=("MS Gothic", 9, "bold"), foreground="#27ae60", cursor="hand2")
        self.lbl_stat_chats.pack(side="left", padx=6, expand=True)
        self.lbl_stat_chats.bind("<Button-1>", lambda e: show_detected_chats_report(self))

        self.lbl_stat_linked = ttk.Label(self.board_lf, text="🖼️ 紐づけ成功: 待機中...", font=("MS Gothic", 9, "bold"), foreground="#e67e22", cursor="hand2")
        self.lbl_stat_linked.pack(side="left", padx=6, expand=True)
        self.lbl_stat_linked.bind("<Button-1>", lambda e: show_linked_assets_report(self))

        self.lbl_stat_stray = ttk.Label(self.board_lf, text="❓ 迷子アセット: 待機中...", font=("MS Gothic", 9, "bold"), foreground="#c0392b", cursor="hand2")
        self.lbl_stat_stray.pack(side="left", padx=6, expand=True)
        self.lbl_stat_stray.bind("<Button-1>", lambda e: show_missing_assets_report(self))

        self.lbl_stat_duplicate = ttk.Label(self.board_lf, text="⚛️ 重複: 待機中...", font=("MS Gothic", 9, "bold"), foreground="#8e44ad", cursor="hand2")
        self.lbl_stat_duplicate.pack(side="left", padx=6, expand=True)
        self.lbl_stat_duplicate.bind("<Button-1>", lambda e: show_duplicate_assets_report(self))

        self.lbl_stat_missing = ttk.Label(self.board_lf, text="❌ 行方不明(Missing): 待機中...", font=("MS Gothic", 9, "bold"), foreground="#c0392b", cursor="hand2")
        self.lbl_stat_missing.pack(side="left", padx=6, expand=True)
        self.lbl_stat_missing.bind("<Button-1>", lambda e: show_missing_links_report(self))

        self.progress_bar = ttk.Progressbar(self.settings_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=4, padx=5)

        # 2. Treeviewフレーム構築
        tree_ctrl = ttk.Frame(self.tree_frame)
        tree_ctrl.pack(fill="x", side="top", pady=2)
        ttk.Button(tree_ctrl, text="全選択", command=self.select_all_tree_items).pack(side="left", padx=5)
        ttk.Button(tree_ctrl, text="全解除", command=self.deselect_all_tree_items).pack(side="left", padx=2)

        tree_content_f = ttk.Frame(self.tree_frame)
        tree_content_f.pack(fill="both", expand=True, side="top")

        self.tree = ttk.Treeview(tree_content_f, columns=("Check", "State", "Title", "Service", "Time", "Assets_Linked", "Assets_Dup", "Assets_Missing"), show="headings", selectmode="browse")
        self.tree.heading("Check", text="選択")
        self.tree.heading("State", text="状態")
        self.tree.heading("Title", text="チャットの題名")
        self.tree.heading("Service", text="サービス種類")
        self.tree.heading("Time", text="最終更新時刻")
        self.tree.heading("Assets_Linked", text="成功")
        self.tree.heading("Assets_Dup", text="重複")
        self.tree.heading("Assets_Missing", text="Missing")

        self.tree.column("Check", width=40, anchor="center")
        self.tree.column("State", width=70, anchor="center")
        self.tree.column("Title", width=250, anchor="w")
        self.tree.column("Service", width=110, anchor="center")
        self.tree.column("Time", width=140, anchor="center")
        self.tree.column("Assets_Linked", width=60, anchor="center")
        self.tree.column("Assets_Dup", width=60, anchor="center")
        self.tree.column("Assets_Missing", width=65, anchor="center")
        self.tree.pack(fill="both", expand=True, side="left")

        ysb = ttk.Scrollbar(tree_content_f, orient="vertical", command=self.tree.yview)
        ysb.pack(fill="y", side="right")
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.tag_configure("success", background="#e2f0d9")

        # 3. ログフレーム構築
        log_content_f = ttk.Frame(self.log_frame)
        log_content_f.pack(fill="both", expand=True, side="top")
        self.log_text = tk.Text(log_content_f, background="#1e1e1e", fg="#a0db86", font=("MS Gothic", 9))
        self.log_text.pack(fill="both", expand=True, side="left")
        sb_log = ttk.Scrollbar(log_content_f, command=self.log_text.yview)
        sb_log.pack(fill="y", side="right")
        self.log_text.configure(yscrollcommand=sb_log.set)

        # 4. プレビューフレーム構築
        preview_header = ttk.Frame(self.preview_frame)
        preview_header.pack(fill="x", side="top", pady=2)
        ttk.Label(preview_header, text="📖 本文 ＆ 診断レポート表示", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)

        self.btn_popout = ttk.Button(preview_header, text="🪟 別窓で表示", command=self.popout_current_view)
        self.btn_popout.pack(side="left", padx=4)

        self.btn_open_report_temp = ttk.Button(preview_header, text="📁 対象ファイルを一時フォルダで確認", command=self.open_current_report_temp_dir, state="disabled")
        self.btn_open_report_temp.pack(side="left", padx=4)

        self.var_rich_preview = tk.BooleanVar(value=True)
        ttk.Checkbutton(preview_header, text="マークダウン装飾", variable=self.var_rich_preview, command=self.update_inline_preview).pack(side="right", padx=10)

        preview_content_f = ttk.Frame(self.preview_frame)
        preview_content_f.pack(fill="both", expand=True, side="top")
        self.preview_text = tk.Text(preview_content_f, background="#ffffff", wrap="word")
        self.preview_text.pack(fill="both", expand=True, side="left")
        sb_prev_inline = ttk.Scrollbar(preview_content_f, command=self.preview_text.yview)
        sb_prev_inline.pack(fill="y", side="right")
        self.preview_text.configure(yscrollcommand=sb_prev_inline.set)
        self.preview_text.insert(tk.END, "💡 リストからチャットを選択するか、上の診断ボードをクリックすると、ここにプレビューが表示されます。")
        self.preview_text.config(state="disabled")

        self.after(500, self.bind_geometry_tracker)
        self.rebuild_layout()
        self.setup_drag_and_drop()

    def set_report_button_state(self, enabled=True):
        if enabled:
            self.btn_open_report_temp.config(state="normal")
        else:
            self.btn_open_report_temp.config(state="disabled")

    def popout_current_view(self):
        if getattr(self, 'current_view_state', 'chat') == 'report':
            report_type = getattr(self, 'current_report_type', '診断レポート')
            report_md = getattr(self, 'last_rendered_report_md', '')
            if report_md:
                show_report_popout_window(self, report_type, report_md, self.apply_window_icon)
        else:
            sel = self.tree.selection()
            if sel:
                idx = int(sel[0])
                if idx < len(self.scanned_chats_data):
                    show_chat_preview_dialog(self, self.scanned_chats_data[idx], self.apply_window_icon)

    def open_current_report_temp_dir(self):
        src = self.src_dir_var.get().strip()
        if not src or not os.path.exists(src):
            messagebox.showwarning("警告", "インポート元フォルダが指定されていません。")
            return

        report_type = getattr(self, 'current_report_type', 'chat_body')

        if report_type == "総ファイル数":
            try: os.startfile(src)
            except: pass
            return

        if "Missing" in report_type or "行方不明" in report_type:
            messagebox.showinfo("情報", "行方不明(Missing)アセットは物理ファイルが存在しないため抽出できません。")
            return

        temp_dir = os.path.join(CURRENT_DIR, "__preview_report_temp")
        if os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass
        os.makedirs(temp_dir, exist_ok=True)

        target_files = []
        if "検出チャット" in report_type:
            target_files = [item.get("file_name") for item in self.scanned_chats_data if item.get("file_name")]
        elif "紐づけ成功" in report_type:
            target_files = list(self.last_linked_assets)
        elif "迷子" in report_type:
            target_files = list(self.last_missing_assets)
        elif "重複" in report_type:
            target_files = []
            for f_hash, files in self.last_duplicate_map.items():
                if len(files) > 1:
                    target_files.extend(files)

        copied = 0
        for fn in target_files:
            sp = os.path.join(src, fn)
            dp = os.path.join(temp_dir, fn)
            if os.path.exists(sp):
                try:
                    shutil.copy2(sp, dp)
                    copied += 1
                except: pass

        self.log(f"📁 [対象抽出] 『{report_type}』の対象ファイル {copied} 件を一時フォルダ 『__preview_report_temp』 に展開して開きます。")
        try: os.startfile(temp_dir)
        except Exception as e:
            messagebox.showinfo("展開完了", f"一時フォルダに展開しました:\n{temp_dir}")

    def bind_geometry_tracker(self):
        try:
            top_win = self.winfo_toplevel()
            top_win.bind("<Configure>", self.on_window_configure)
        except: pass

    def on_window_configure(self, event):
        try:
            top_win = self.winfo_toplevel()
            if top_win.state() == 'normal':
                self.last_normal_geometry = top_win.geometry()
        except: pass

    def setup_window_close_hook(self):
        try:
            top_win = self.winfo_toplevel()
            top_win.protocol("WM_DELETE_WINDOW", self.on_app_close)
            self.apply_window_icon(top_win)
        except: pass

    def rebuild_layout(self):
        for w in [self.settings_frame, self.tree_frame, self.log_frame, self.preview_frame]:
            try: w.pack_forget()
            except: pass

        if hasattr(self, 'pane') and self.pane:
            try: self.pane.destroy()
            except: pass

        mode = self.layout_mode_var.get()
        side = self.pane_side_var.get()
        show_prev = self.var_show_preview.get()
        show_log = self.var_show_log.get()

        cfg = load_config()
        cfg["importer_layout_mode"] = mode
        cfg["importer_pane_side"] = side
        cfg["importer_show_preview"] = show_prev
        cfg["importer_show_log"] = show_log
        save_config_data(cfg)

        if mode == "vertical":
            self.settings_frame.pack(in_=self.main_container, fill="x", side="top", pady=2)

            self.pane = tk.PanedWindow(self.main_container, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
            self.pane.pack(fill="both", expand=True, side="bottom")

            box_tree = ttk.Frame(self.pane)
            self.tree_frame.pack(in_=box_tree, fill="both", expand=True)
            self.pane.add(box_tree, stretch="always", minsize=140)

            if show_prev:
                box_prev = ttk.Frame(self.pane)
                self.preview_frame.pack(in_=box_prev, fill="both", expand=True)
                self.pane.add(box_prev, stretch="always", minsize=120)

            if show_log:
                box_log = ttk.Frame(self.pane)
                self.log_frame.pack(in_=box_log, fill="both", expand=True)
                self.pane.add(box_log, stretch="always", minsize=100)

        elif mode == "horizontal_2":
            self.pane = tk.PanedWindow(self.main_container, orient=tk.HORIZONTAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
            self.pane.pack(fill="both", expand=True)

            self.left_pane = tk.PanedWindow(self.pane, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
            box_set = ttk.Frame(self.left_pane)
            box_tree = ttk.Frame(self.left_pane)
            self.settings_frame.pack(in_=box_set, fill="both", expand=True)
            self.tree_frame.pack(in_=box_tree, fill="both", expand=True)
            self.left_pane.add(box_set, minsize=220)
            self.left_pane.add(box_tree, stretch="always", minsize=140)

            has_sub = show_prev or show_log
            if has_sub:
                self.right_pane = tk.PanedWindow(self.pane, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
                if show_prev:
                    box_prev = ttk.Frame(self.right_pane)
                    self.preview_frame.pack(in_=box_prev, fill="both", expand=True)
                    self.right_pane.add(box_prev, stretch="always", minsize=140)
                if show_log:
                    box_log = ttk.Frame(self.right_pane)
                    self.log_frame.pack(in_=box_log, fill="both", expand=True)
                    self.right_pane.add(box_log, stretch="always", minsize=100)

            if side == "right":
                self.pane.add(self.left_pane, stretch="always", minsize=350)
                if has_sub: self.pane.add(self.right_pane, stretch="always", minsize=350)
            else:
                if has_sub: self.pane.add(self.right_pane, stretch="always", minsize=350)
                self.pane.add(self.left_pane, stretch="always", minsize=350)

        elif mode == "horizontal_3":
            self.pane = tk.PanedWindow(self.main_container, orient=tk.HORIZONTAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
            self.pane.pack(fill="both", expand=True)

            self.left_pane = tk.PanedWindow(self.pane, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
            box_set = ttk.Frame(self.left_pane)
            box_tree = ttk.Frame(self.left_pane)
            self.settings_frame.pack(in_=box_set, fill="both", expand=True)
            self.tree_frame.pack(in_=box_tree, fill="both", expand=True)
            self.left_pane.add(box_set, minsize=220)
            self.left_pane.add(box_tree, stretch="always", minsize=140)

            box_prev = ttk.Frame(self.pane) if show_prev else None
            if box_prev: self.preview_frame.pack(in_=box_prev, fill="both", expand=True)

            box_log = ttk.Frame(self.pane) if show_log else None
            if box_log: self.log_frame.pack(in_=box_log, fill="both", expand=True)

            if side == "right":
                self.pane.add(self.left_pane, stretch="always", minsize=300)
                if box_prev: self.pane.add(box_prev, stretch="always", minsize=280)
                if box_log: self.pane.add(box_log, stretch="always", minsize=220)
            else:
                if box_log: self.pane.add(box_log, stretch="always", minsize=220)
                if box_prev: self.pane.add(box_prev, stretch="always", minsize=280)
                self.pane.add(self.left_pane, stretch="always", minsize=300)

        if hasattr(self, 'log'):
            self.log(f"🖥️ 画面レイアウト更新 (モード: {mode} / 配置: {side})")

    def save_window_geometry(self):
        try:
            top_win = self.winfo_toplevel()
            cfg = load_config()

            is_maximized = (top_win.state() == 'zoomed')
            cfg["importer_is_maximized"] = is_maximized

            x = top_win.winfo_x()
            y = top_win.winfo_y()
            cfg["importer_maximized_pos"] = f"+{x}+{y}"

            if hasattr(self, 'last_normal_geometry') and self.last_normal_geometry:
                cfg["importer_window_geometry"] = self.last_normal_geometry
            elif not is_maximized:
                cfg["importer_window_geometry"] = top_win.geometry()

            save_config_data(cfg)
        except: pass

    def toggle_run_mode(self):
        mode = self.run_mode_var.get()
        self.log(f"⚙️ インポート実行モードを『{mode}』に切り替えました。")

    def log(self, message):
        if not hasattr(self, 'log_text') or not self.log_text:
            print(message); return
        try:
            self.log_text.config(state="normal")
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{now}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        except: pass

    def update_dashboard_counts(self, total, chats, linked, stray, duplicate=0, missing=0):
        self.lbl_stat_total.config(text=f"📂 総ファイル数: {total} 件")
        self.lbl_stat_chats.config(text=f"💬 検出チャット: {chats} 件")

        if self.is_analyzed:
            self.lbl_stat_linked.config(text=f"🖼️ 紐づけ成功: {linked} 件")
            self.lbl_stat_stray.config(text=f"❓ 迷子アセット: {stray} 件")
            self.lbl_stat_duplicate.config(text=f"⚛️ 重複: {duplicate} 件")
            self.lbl_stat_missing.config(text=f"❌ 行方不明(Missing): {missing} 件")
        else:
            self.lbl_stat_linked.config(text="🖼️ 紐づけ成功: 解析待ち")
            self.lbl_stat_stray.config(text="❓ 迷子アセット: 解析待ち")
            self.lbl_stat_duplicate.config(text="⚛️ 重複: 解析待ち")
            self.lbl_stat_missing.config(text="❌ 行方不明(Missing): 解析待ち")

    def open_source_dir_in_explorer(self):
        src = self.src_dir_var.get().strip()
        if src and os.path.exists(src):
            try: os.startfile(src)
            except: pass

    def on_combo_select(self, event):
        if self.service_var.get() == "新規追加...":
            self.new_svc_frame.pack(side="left", padx=5)
        else:
            self.new_svc_frame.pack_forget()

    def select_source_dir(self):
        path = filedialog.askdirectory(title="インポート元フォルダの選択")
        if path:
            path = os.path.abspath(path)
            self.src_dir_var.set(path)
            self.log(f"📂 インポート元フォルダを設定しました: {path}")

    def select_dest_dir(self):
        path = filedialog.askdirectory(title="インポート先（保存先）フォルダの選択")
        if path:
            path = os.path.abspath(path)
            self.dest_dir_var.set(path)
            self.log(f"📂 インポート先（保存先）フォルダを設定しました: {path}")

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell": return

        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item_id: return

        if column == "#1":
            current = self.tree.item(item_id, "values")
            new_check = "☐" if current[0] == "☑" else "☑"
            self.tree.item(item_id, values=(new_check, current[1], current[2], current[3], current[4], current[5], current[6], current[7]))
            return

        idx = int(item_id)
        if idx >= len(self.scanned_chats_data): return
        chat_item = self.scanned_chats_data[idx]

        if column == "#6" and self.is_analyzed:
            self.current_view_state = "report"
            show_single_chat_detail_report(self, chat_item, "成功")
            return

        elif column == "#7" and self.is_analyzed:
            self.current_view_state = "report"
            show_single_chat_detail_report(self, chat_item, "重複")
            return

        elif column == "#8" and self.is_analyzed:
            self.current_view_state = "report"
            show_single_chat_detail_report(self, chat_item, "Missing")
            return

    def select_all_tree_items(self):
        for item_id in self.tree.get_children():
            current = self.tree.item(item_id, "values")
            if len(current) >= 8:
                self.tree.item(item_id, values=("☑", current[1], current[2], current[3], current[4], current[5], current[6], current[7]))

    def deselect_all_tree_items(self):
        for item_id in self.tree.get_children():
            current = self.tree.item(item_id, "values")
            if len(current) >= 8:
                self.tree.item(item_id, values=("☐", current[1], current[2], current[3], current[4], current[5], current[6], current[7]))

    def on_tree_select(self, event):
        if getattr(self, 'current_view_state', 'chat') == 'report':
            return
            
        self.current_view_state = "chat"
        self.set_report_button_state(False)
        self.update_inline_preview()

    def update_inline_preview(self):
        if getattr(self, 'current_view_state', 'chat') == 'report':
            if hasattr(self, 'last_rendered_report_md') and self.last_rendered_report_md:
                render_clean_report_markdown(self.preview_text, self.last_rendered_report_md, self.var_rich_preview.get())
                self.preview_text.config(state="disabled")
                return

        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        if idx >= len(self.scanned_chats_data): return
        item = self.scanned_chats_data[idx]

        raw_preview_md = ["---", f"title: \"{item['title']}\"", f"service: \"{item['service']}\"", "---"]
        for turn in item.get("parsed_contents", []):
            role = turn.get("role", "unknown")
            disp_role = "👤 USER" if role == "user" else "🤖 MODEL"
            parts = turn.get("parts", [])
            part_text = ""
            for p in parts:
                if isinstance(p, dict) and "text" in p: part_text += p["text"] + "\n"
            if part_text.strip(): raw_preview_md.append(f"### {disp_role}\n{part_text.strip()}\n")

        self.last_rendered_chat_md = "\n".join(md for md in raw_preview_md)
        self.current_view_state = "chat"
        self.set_report_button_state(False)
        render_chat_markdown(self.preview_text, self.last_rendered_chat_md, self.var_rich_preview.get())
        self.preview_text.config(state="disabled")

    def on_tree_double_click(self, event):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        if idx < len(self.scanned_chats_data):
            show_chat_preview_dialog(self, self.scanned_chats_data[idx], self.apply_window_icon)

    def on_app_close(self):
        self.save_window_geometry()
        confirm_app_close(self, CURRENT_DIR)

    def setup_drag_and_drop(self):
        try:
            import windnd
            def on_drag_dropped(files):
                if files:
                    path = files[0].decode("utf-8") if isinstance(files[0], bytes) else files[0]
                    if os.path.isdir(path):
                        self.src_dir_var.set(path)
                        self.log(f"📂 ドラッグ＆ドロップでインポート元フォルダを設定しました: {path}")
            windnd.hook_dropfiles(self.winfo_toplevel(), func=on_drag_dropped)
        except: pass


# ================= 🖥️ 単体起動時のテストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("🔨 AiReLinkerImporter - インポーター（完全統合版）")

    cfg = load_config()
    saved_geom = cfg.get("importer_window_geometry", "950x680")
    is_maximized = cfg.get("importer_is_maximized", False)
    max_pos = cfg.get("importer_maximized_pos", "")

    try: root.geometry(saved_geom)
    except: root.geometry("950x680")

    if is_maximized:
        if max_pos:
            try:
                w_h = saved_geom.split('+')[0]
                root.geometry(f"{w_h}{max_pos}")
                root.update_idletasks()
            except: pass
        try: root.state('zoomed')
        except: pass

    importer_frame = AiReLinkerImporterFrame(root, None)
    importer_frame.pack(fill="both", expand=True, padx=10, pady=10)
    importer_frame.apply_window_icon(root)

    root.mainloop()