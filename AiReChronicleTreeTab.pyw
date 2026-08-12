# -*- coding: utf-8 -*-
# AiReChronicleTreeTab.pyw - 開発史クロノツリー (マルチスレッド並列爆速スキャン・専用保存ボタン＆テーマ名保護完成版)
import sys
import os
import re
import json
import datetime
import shutil
import importlib.util
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --- 🌟 日本語形態素解析ライブラリ Janome の安全読み込み ---
JANOME_AVAILABLE = False
try:
    from janome.tokenizer import Tokenizer
    JANOME_AVAILABLE = True
except ImportError:
    pass

# --- 0. ポータブル環境 ＆ ライブラリパス安全設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

# --- 1. エンジンモジュール (AiReChronicleTreeEngine.pyw) の動的インポート ---
HAS_ENGINE = False
AiReChronicleEngine = None
ChronicleTreeControlFrame = None
ENGINE_ERROR_MSG = ""

engine_path = os.path.join(CURRENT_DIR, "AiReChronicleTreeEngine.pyw")
if os.path.exists(engine_path):
    try:
        spec = importlib.util.spec_from_file_location("AiReChronicleTreeEngine", engine_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        AiReChronicleEngine = getattr(mod, "AiReChronicleEngine")
        ChronicleTreeControlFrame = getattr(mod, "ChronicleTreeControlFrame")
        HAS_ENGINE = True
    except Exception as e:
        ENGINE_ERROR_MSG = f"エンジンロードエラー: {e}"
else:
    ENGINE_ERROR_MSG = "AiReChronicleTreeEngine.pyw が同じフォルダに見つかりません。"

# --- 2. 外部マークダウンビューアーの安全インポート ---
try:
    from AiReAnchorMarkdownViewer import render_rich_markdown
    HAS_MD_VIEWER = True
except ImportError:
    HAS_MD_VIEWER = False
    def render_rich_markdown(text_widget, raw_text, base_dir=None, show_rich=True, show_images=True, image_refs_list=None, filepath=None, show_style="simple"):
        text_widget.config(state="normal")
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", raw_text if raw_text else "（表示するデータがありません）")
        text_widget.config(state="disabled")

# Windows AppID 登録
try:
    import ctypes
    myappid = 'airelinker.suite.chronicle.v8'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


class AiReChronicleTreeFrame(ttk.Frame):
    """3パネル高圧縮＆階層型目次生成フレーム (マルチスレッド並列爆速スキャン・UI特化版)"""

    def __init__(self, parent, save_dir=None, main_app=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.config = self.load_config()
        if main_app and hasattr(main_app, "save_dir"):
            self.save_dir = main_app.save_dir
        else:
            self.save_dir = save_dir if save_dir else self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))

        self.is_custom_external_mode = False
        self.custom_external_path = ""

        self.my_rag_dir = os.path.join(self.save_dir, "my_RAG_Vault")
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(self.my_rag_dir, exist_ok=True)

        # エンジンのインスタンス化
        self.engine = AiReChronicleEngine() if HAS_ENGINE else None

        self.custom_tags = []
        self.active_tag_indices = set()
        self.excluded_chats = set()

        self.tag_history = self.config.get("chronicle_tag_history", [])

        self.chat_checks = {}        # {chat_path: True/False}
        self.folder_checks = {}      # {folder_name: True/False}
        self.chat_relevances = {}    # {chat_path: (score, label)}

        # 🌟 ユーザー手入力テーマ名の保護フラグ（書き換え後は自動生成で上書きしない）
        self.user_edited_theme = False

        self.font_main = ("Yu Gothic UI", 10)
        self.font_code = ("Meiryo", 10)

        self.raw_text = ""
        self.step_result_cache = ""

        self.current_match_indices = []
        self.current_match_pos = 0

        self._setup_ui()
        self.refresh_chat_tree()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}

    def save_config_state(self):
        self.config["chronicle_tag_history"] = self.tag_history[:500]
        if self.main_app and hasattr(self.main_app, "save_config"):
            self.main_app.save_config()
        else:
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            except: pass

    def find_summary_file_path(self, chat_path):
        if not chat_path: return None
        if os.path.isfile(chat_path): return None
        
        chat_name = os.path.basename(chat_path)
        candidates = [
            os.path.join(chat_path, f"summary_{chat_name}.md"),
            os.path.join(chat_path, "summary.md"),
            os.path.join(chat_path, "summary_master.md")
        ]
        for cand in candidates:
            if os.path.exists(cand): return cand
        for f in os.listdir(chat_path):
            if f.startswith("summary_") and f.endswith(".md"):
                return os.path.join(chat_path, f)
        return None

    def _setup_ui(self):
        top_bar = ttk.Frame(self, padding=(4, 2))
        top_bar.pack(fill="x", side="top")

        ttk.Button(top_bar, text="📄 単一ファイル参照...", command=self.browse_single_file).pack(side="left", padx=2)
        ttk.Button(top_bar, text="📁 外部フォルダ一括参照...", command=self.browse_external_dir).pack(side="left", padx=2)
        ttk.Button(top_bar, text="↩ システム標準に戻す", command=self.restore_system_default_dir).pack(side="left", padx=4)

        self.lbl_ext_path = ttk.Label(top_bar, text="", font=("Yu Gothic UI", 9, "bold"), foreground="#ea580c")
        self.lbl_ext_path.pack(side="left", padx=6)

        self.lbl_default_path = ttk.Label(top_bar, text=f"現在参照中: [ {self.save_dir} ]", font=("Yu Gothic UI", 9, "bold"), foreground="#0284c7")
        self.lbl_default_path.pack(side="left", padx=6)

        ttk.Button(top_bar, text="🔄 再ロード", command=self.refresh_chat_tree).pack(side="right", padx=2)

        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill="both", expand=True, padx=4, pady=4)

        # =========================================================================
        # 左パネル: 1. 対象ログ選択 ＆ タグフィルタ ＆ 【生データ転送ボタン】
        # =========================================================================
        left_p = ttk.Frame(self.main_pane, width=330)
        self.main_pane.add(left_p, weight=1)

        left_v_pane = ttk.Panedwindow(left_p, orient=tk.VERTICAL)
        left_v_pane.pack(fill="both", expand=True)

        tree_lf = ttk.LabelFrame(left_v_pane, text=" 🎛 1. 年表対象ログ選択 ＆ タグフィルタ ", padding=6)
        left_v_pane.add(tree_lf, weight=4)

        filter_f = ttk.Frame(tree_lf)
        filter_f.pack(fill="x", pady=(0, 2))
        self.var_filter_candidates = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_f, text="☑ 引き継ぎログのみ表示", variable=self.var_filter_candidates, command=self.refresh_chat_tree).pack(side="left")

        act_bar = ttk.Frame(tree_lf)
        act_bar.pack(fill="x", pady=2)
        ttk.Button(act_bar, text="☑ 全選択", command=self.select_all_chats).pack(side="left", padx=1)
        ttk.Button(act_bar, text="☐ 全解除", command=self.deselect_all_chats).pack(side="left", padx=1)
        ttk.Button(act_bar, text="🧹 全除外", command=self.clear_all_chats).pack(side="left", padx=1)
        ttk.Button(act_bar, text="➕ 追加", command=self.add_chat_manually).pack(side="left", padx=1)
        ttk.Button(act_bar, text="❌ 未選択を除外", command=self.remove_unselected_chats).pack(side="left", padx=1)

        # 生データの外部連携ボタン群
        act_bar2 = ttk.Frame(tree_lf)
        act_bar2.pack(fill="x", pady=4)
        ttk.Button(act_bar2, text="🔨 選択チャット(生)を Forge タブへ送る", command=self.send_raw_to_forge).pack(fill="x", pady=1)
        ttk.Button(act_bar2, text="🧭 選択チャット(生)を Compass タブへ送る", command=self.send_raw_to_compass).pack(fill="x", pady=1)
        ttk.Button(act_bar2, text="📦 選択チャット(生)を無加工で外部コピー保存", command=self.export_unprocessed_to_external_folder).pack(fill="x", pady=1)

        tag_in_f = ttk.Frame(tree_lf)
        tag_in_f.pack(fill="x", pady=4)
        ttk.Label(tag_in_f, text="タグ検索:", font=self.font_main).pack(side="left", padx=2)
        self.entry_tag = ttk.Entry(tag_in_f, font=self.font_main)
        self.entry_tag.pack(side="left", fill="x", expand=True, padx=2)
        self.entry_tag.bind("<Return>", lambda e: self.add_custom_tag())
        ttk.Button(tag_in_f, text="＋タグ追加", command=self.add_custom_tag).pack(side="left", padx=2)

        self.chip_frame = ttk.Frame(tree_lf)
        self.chip_frame.pack(fill="x", pady=2)
        self._redraw_tag_chips()

        tree_container = ttk.Frame(tree_lf)
        tree_container.pack(fill="both", expand=True, pady=2)

        self.tree_chats = ttk.Treeview(tree_container, show="tree", selectmode="browse")
        sb_tree = ttk.Scrollbar(tree_container, command=self.tree_chats.yview)
        self.tree_chats.configure(yscrollcommand=sb_tree.set)
        self.tree_chats.pack(side="left", fill="both", expand=True)
        sb_tree.pack(side="right", fill="y")
        self.tree_chats.bind("<Button-1>", self.on_tree_click)

        hist_f = ttk.LabelFrame(left_v_pane, text=" 📜 過去のタグ検索履歴 ", padding=4)
        left_v_pane.add(hist_f, weight=1)

        hist_btn_bar = ttk.Frame(hist_f)
        hist_btn_bar.pack(fill="x", pady=(0, 2))
        ttk.Button(hist_btn_bar, text="🗑️ 選択履歴削除", command=self.delete_selected_history).pack(side="left", padx=1)
        ttk.Button(hist_btn_bar, text="🧹 全履歴消去", command=self.clear_all_history).pack(side="right", padx=1)

        self.history_listbox = tk.Listbox(hist_f, background="#f8fafc", font=("Yu Gothic UI", 8), height=3)
        self.history_listbox.pack(fill="both", expand=True)
        self.history_listbox.bind("<Double-Button-1>", self.on_history_double_click)

        stats_lf = ttk.LabelFrame(left_p, text=" 📊 選択ログ統計インジケーター ", padding=6)
        stats_lf.pack(fill="x", side="bottom", pady=4)
        self.lbl_stats_count = ttk.Label(stats_lf, text="・ 表示数: 0 件 ／ 選択数: 0 件", font=("Yu Gothic UI", 9))
        self.lbl_stats_count.pack(anchor="w", pady=1)
        self.lbl_stats_chars = ttk.Label(stats_lf, text="・ 生ログ文字数: 選択 0 字 (全体 0 字)", font=("Yu Gothic UI", 9, "bold"), foreground="#0284c7")
        self.lbl_stats_chars.pack(anchor="w", pady=1)

        # 🌟 月の満ち欠け凡例表示を維持
        ttk.Label(stats_lf, text="※ 凡例: 🌕高(80%+), 🌓中(30-79%), 🌒低(3-29%), 🌑無(0-2%)", font=("Yu Gothic UI", 8), foreground="#64748b").pack(anchor="w", pady=(2, 0))

        # =========================================================================
        # 中央パネル: 2. 出力設定 ＆ 成果物プレビュービューアー
        # =========================================================================
        center_p = ttk.Frame(self.main_pane, width=460)
        self.main_pane.add(center_p, weight=3)

        out_lf = ttk.LabelFrame(center_p, text=" 📌 2. 出力設定 ＆ 成果物プレビュー ", padding=6)
        out_lf.pack(fill="both", expand=True, pady=2)

        out_cfg_f = ttk.Frame(out_lf)
        out_cfg_f.pack(fill="x", pady=2)
        row_d = ttk.Frame(out_cfg_f)
        row_d.pack(fill="x", pady=1)
        ttk.Label(row_d, text="保存フォルダ:", font=self.font_main, width=11).pack(side=tk.LEFT)
        self.entry_out_dir = ttk.Entry(row_d, font=self.font_main)
        self.entry_out_dir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.entry_out_dir.insert(0, self.my_rag_dir)
        ttk.Button(row_d, text="📂 変更...", command=self.browse_out_dir).pack(side=tk.RIGHT, padx=2)

        row_f = ttk.Frame(out_cfg_f)
        row_f.pack(fill="x", pady=1)
        ttk.Label(row_f, text="出力テーマ名:", font=self.font_main, width=11).pack(side=tk.LEFT)
        self.entry_out_filename = ttk.Entry(row_f, font=self.font_main)
        self.entry_out_filename.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        # 🌟 ユーザーの手入力を検知して自動上書きを停止するイベントバインド
        self.entry_out_filename.bind("<Key>", self.on_theme_name_user_key)

        nav_bar = ttk.Frame(out_lf)
        nav_bar.pack(fill="x", pady=2)

        self.view_target_var = tk.StringVar(value="result")
        ttk.Radiobutton(nav_bar, text="📄 変換前(生データ)", variable=self.view_target_var, value="raw", command=self.reload_preview_style).pack(side="left", padx=2)
        ttk.Radiobutton(nav_bar, text="📜 変換後(圧縮結果)", variable=self.view_target_var, value="result", command=self.reload_preview_style).pack(side="left", padx=2)
        ttk.Label(nav_bar, text="|", font=self.font_main, foreground="#cbd5e1").pack(side="left", padx=2)

        self.style_var = tk.StringVar(value="simple")
        ttk.Radiobutton(nav_bar, text="標準MD", variable=self.style_var, value="simple", command=self.reload_preview_style).pack(side="left", padx=1)
        ttk.Radiobutton(nav_bar, text="AiRe装飾", variable=self.style_var, value="aire", command=self.reload_preview_style).pack(side="left", padx=1)
        ttk.Radiobutton(nav_bar, text="装飾OFF", variable=self.style_var, value="none", command=self.reload_preview_style).pack(side="left", padx=1)

        self.img_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(nav_bar, text="画像表示", variable=self.img_var, command=self.reload_preview_style).pack(side="left", padx=2)
        
        self.lbl_nav_count = ttk.Label(nav_bar, text="[ 0 / 0 件目 ]", font=("Yu Gothic UI", 8, "bold"), foreground="#0284c7")
        self.lbl_nav_count.pack(side="left", padx=4)
        ttk.Button(nav_bar, text="↑ 前へ", width=4, command=self.jump_prev_match).pack(side="left", padx=1)
        ttk.Button(nav_bar, text="↓ 次へ", width=4, command=self.jump_next_match).pack(side="left", padx=1)
        ttk.Button(nav_bar, text="🔍 検索 (Ctrl+F)", command=self.trigger_ctrl_f_search).pack(side="right", padx=2)

        prev_txt_f = ttk.Frame(out_lf)
        prev_txt_f.pack(fill="both", expand=True, pady=4)

        self.output_text = tk.Text(prev_txt_f, wrap=tk.WORD, font=self.font_code, bg="#F8F9FA")
        sb_prev = ttk.Scrollbar(prev_txt_f, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=sb_prev.set)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_prev.pack(side=tk.RIGHT, fill=tk.Y)

        # =========================================================================
        # 右パネル: 3. コア調整パラメータ ＆ 実行オーケストレーター ＆ 【ワンクリック保存ボタン群】
        # =========================================================================
        right_p = ttk.Frame(self.main_pane, width=380)
        self.main_pane.add(right_p, weight=2)

        if HAS_ENGINE and self.engine:
            # 🌟 正確な引数（parent, engine_instance, コールバック群）で100%安全にエンジンUIをドッキング！
            self.control_frame = ChronicleTreeControlFrame(
                parent=right_p,
                engine_instance=self.engine,
                get_source_cb=self.collect_selected_texts,
                update_preview_cb=self.update_preview_from_engine,
                save_vault_cb=lambda: self.save_chronicle_to_vault(mode="both"),
                send_forge_cb=self.send_compressed_to_forge,
                send_compass_cb=self.send_compressed_to_compass
            )
            self.control_frame.pack(fill="both", expand=True)

            # 🌟 「最終結果を my_RAG_Vault へ一括保存」ボタンのすぐ下に追加の個別保存ボタンを直接配置！
            sub_save_lf = ttk.LabelFrame(self.control_frame, text=" 💾 my_RAG_Vault 部分別ワンクリック保存 ", padding=4)
            sub_save_lf.pack(fill="x", pady=4, padx=4)

            ttk.Button(sub_save_lf, text="📜 クロノツリー全景マップ（年表目次）のみ保存", command=lambda: self.save_chronicle_to_vault(mode="master")).pack(fill="x", pady=2)
            ttk.Button(sub_save_lf, text="📁 各チャットの個別圧縮枝葉のみ保存", command=lambda: self.save_chronicle_to_vault(mode="branches")).pack(fill="x", pady=2)

            # 🌟 右下のシステムログせり上がり防止（ボタン領域の高さを自動固定・保護）
            self.after(250, self.adjust_right_log_position)
        else:
            err_lbl = ttk.Label(right_p, text=f"⚠️ {ENGINE_ERROR_MSG}", foreground="red", font=self.font_main, wraplength=300)
            err_lbl.pack(expand=True)

    def on_theme_name_user_key(self, event):
        """🌟 ユーザーがテーマ名を手入力で編集した場合、自動上書きをロック固定"""
        if event.keysym not in ["Tab", "Shift_L", "Shift_R", "Control_L", "Control_R", "Return", "Escape"]:
            self.user_edited_theme = True

    def adjust_right_log_position(self):
        """🌟 右側PanedWindowの初期仕切り位置（sashpos）を調整してログのせり上がりを抑え、ボタン群を確保"""
        try:
            if hasattr(self, 'control_frame'):
                paned_obj = None
                for child in self.control_frame.winfo_children():
                    if isinstance(child, (tk.PanedWindow, ttk.Panedwindow)):
                        paned_obj = child
                        break
                if paned_obj:
                    paned_obj.update_idletasks()
                    total_h = paned_obj.winfo_height()
                    if total_h > 200:
                        # 🌟 上部エリアを約72%確保し、下部ログのせり上がりを防止
                        paned_obj.sashpos(0, int(total_h * 0.72))
        except: pass

    def trigger_ctrl_f_search(self):
        self.output_text.focus_set()
        self.output_text.event_generate("<Control-f>")

    def browse_single_file(self):
        file_path = filedialog.askopenfilename(
            title="単一Markdownファイルを選択",
            initialdir=self.save_dir,
            filetypes=[("Markdown / Text", "*.md *.txt"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.is_custom_external_mode = True
                self.custom_external_path = file_path
                self.raw_text = content
                self.view_target_var.set("raw")
                self.lbl_ext_path.config(text=f"イレギュラー参照中: [ {os.path.basename(file_path)} ]")
                self.var_filter_candidates.set(False)
                self.refresh_chat_tree()
                self.reload_preview_style()
            except Exception as e:
                messagebox.showerror("読込エラー", f"ファイルの読み込みに失敗しました:\n{e}")

    def browse_external_dir(self):
        selected = filedialog.askdirectory(title="外部ログフォルダを選択", initialdir=self.save_dir)
        if selected:
            self.is_custom_external_mode = True
            self.custom_external_path = selected
            self.lbl_ext_path.config(text=f"イレギュラー参照中: [ {selected} ]")
            self.var_filter_candidates.set(False)
            self.refresh_chat_tree()

    def restore_system_default_dir(self):
        self.is_custom_external_mode = False
        self.custom_external_path = ""
        self.lbl_ext_path.config(text="")
        self.refresh_chat_tree()

    def browse_out_dir(self):
        selected = filedialog.askdirectory(title="保存先フォルダを選択", initialdir=self.my_rag_dir)
        if selected:
            self.my_rag_dir = selected
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, selected)

    def add_custom_tag(self):
        t = self.entry_tag.get().strip()
        if t and t not in self.custom_tags:
            self.custom_tags.append(t)
            self.entry_tag.delete(0, tk.END)
            self.active_tag_indices.add(len(self.custom_tags) - 1)
            if t in self.tag_history: self.tag_history.remove(t)
            self.tag_history.insert(0, t)
            self.save_config_state()
            self.refresh_history_listbox()
            self._redraw_tag_chips()
            self.update_chat_relevances_only()

    def toggle_active_tag(self, idx):
        if idx in self.active_tag_indices:
            if len(self.active_tag_indices) > 1: self.active_tag_indices.remove(idx)
        else:
            self.active_tag_indices.add(idx)
        self._redraw_tag_chips()
        self.update_chat_relevances_only()

    def remove_custom_tag(self, tag):
        if tag in self.custom_tags:
            idx = self.custom_tags.index(tag)
            self.custom_tags.remove(tag)
            new_indices = set()
            for i in self.active_tag_indices:
                if i < idx: new_indices.add(i)
                elif i > idx: new_indices.add(i - 1)
            self.active_tag_indices = new_indices if new_indices else ({0} if self.custom_tags else set())
            self._redraw_tag_chips()
            self.update_chat_relevances_only()

    def _redraw_tag_chips(self):
        for w in self.chip_frame.winfo_children(): w.destroy()
        for idx, tag in enumerate(self.custom_tags):
            is_active = (idx in self.active_tag_indices)
            f = ttk.Frame(self.chip_frame)
            f.pack(side="left", padx=2, pady=1)
            tk.Button(f, text=f"🏷️ {tag}", bg="#2563eb" if is_active else "#dbeafe", fg="#ffffff" if is_active else "#1e40af", font=("Yu Gothic UI", 8, "bold" if is_active else "normal"), bd=1, relief="sunken" if is_active else "ridge", command=lambda i=idx: self.toggle_active_tag(i)).pack(side="left")
            tk.Button(f, text="✕", bg="#2563eb" if is_active else "#dbeafe", fg="#ffffff" if is_active else "#1e40af", font=("Yu Gothic UI", 8, "bold"), bd=1, relief="flat", command=lambda t=tag: self.remove_custom_tag(t)).pack(side="left")

    def refresh_history_listbox(self):
        self.history_listbox.delete(0, tk.END)
        for tag in self.tag_history:
            self.history_listbox.insert(tk.END, f"🏷️ {tag}")

    def delete_selected_history(self):
        sel = self.history_listbox.curselection()
        if sel:
            idx = sel[0]
            if idx < len(self.tag_history):
                del self.tag_history[idx]
                self.save_config_state()
                self.refresh_history_listbox()

    def clear_all_history(self):
        if messagebox.askyesno("確認", "過去のタグ履歴をすべて消去しますか？"):
            self.tag_history.clear()
            self.save_config_state()
            self.refresh_history_listbox()

    def on_history_double_click(self, event):
        sel = self.history_listbox.curselection()
        if sel:
            selected = self.history_listbox.get(sel[0])
            clean_tag = selected.replace("🏷️ ", "").strip()
            if clean_tag and clean_tag not in self.custom_tags:
                self.custom_tags.append(clean_tag)
                self.active_tag_indices.add(len(self.custom_tags) - 1)
                self._redraw_tag_chips()
                self.update_chat_relevances_only()

    def auto_generate_clean_theme_name(self):
        """🌟 語尾・動詞・助詞を除去し固有名詞・技術名詞のみでスマート命名（ユーザー手入力時は上書き保護）"""
        # ユーザーが一度でも自分で編集した場合は自動上書きしない！
        if self.user_edited_theme:
            return

        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            self.entry_out_filename.delete(0, tk.END)
            self.entry_out_filename.insert(0, "新規クロノツリー")
            return

        selected_titles = [os.path.basename(cp) for cp in selected_paths]
        words = []
        
        # 語尾・口語・一般的な助詞等の除外リスト
        exclude_words = ['こと', 'よう', 'ため', 'やつ', 'これ', 'それ', 'あれ', '感じ', '部分', '方', '件', '他', 'ログ', 'チャット', 'しました', 'です', 'ます', 'について', 'から', 'より', 'とか', 'そう', 'なに', 'なん']

        for chat_title in selected_titles:
            # 1. 不要記号の完全クレンジング
            clean_title = re.sub(r'[＼／：＊？"＜＞｜_\s\[\]\(\)\【\】\「\」]', '', chat_title)
            clean_title = re.sub(r'^(Chronicle_|raw_)', '', clean_title, flags=re.IGNORECASE)
            clean_title = re.sub(r'_他\d+件$', '', clean_title)
            # 2. 会話文末の「〜にしました」「〜です」等を徹底カット
            clean_title = re.sub(r'(にしました|にしましたそ|です|ます|について|と言ったら|とか|について言ったら).*$', '', clean_title)

            if JANOME_AVAILABLE:
                try:
                    tokenizer = Tokenizer()
                    for token in tokenizer.tokenize(clean_title):
                        pos = token.part_of_speech.split(',')[0]
                        surface = token.surface
                        if pos in ['名詞', 'カスタム名詞'] and len(surface) > 1 and surface.lower() not in exclude_words:
                            words.append(surface)
                except: pass
            
            if not words and clean_title:
                words.append(clean_title[:15])

        if words:
            most_common = [w for w, c in Counter(words).most_common(2)]
            theme_name = "_".join(most_common)
        else:
            theme_name = re.sub(r'[＼／：＊？"＜＞｜_\s]', '', selected_titles[0])[:15]

        # 🌟 Chronicle_ や _他21件 などのゴミ文字・プレフィックスを最終二重除去
        theme_name = re.sub(r'^Chronicle_', '', theme_name, flags=re.IGNORECASE)
        theme_name = re.sub(r'_他\d+件$', '', theme_name)
        
        if not theme_name.strip():
            theme_name = "AiReSystem開発"

        self.entry_out_filename.delete(0, tk.END)
        self.entry_out_filename.insert(0, theme_name)

    def _worker_calc_relevance(self, chat_path, active_tags):
        """🌟 マルチスレッド用 1チャットのタグスコア・バッジ計算ワーカー"""
        sample_text = ""
        if os.path.isfile(chat_path):
            try:
                with open(chat_path, "r", encoding="utf-8", errors="ignore") as f: sample_text = f.read()
            except: pass
        else:
            raw_p = os.path.join(chat_path, "raw_master.md")
            if not os.path.exists(raw_p):
                for sk in ["importer", "scraped", "3rd"]:
                    sp = os.path.join(chat_path, sk)
                    if os.path.exists(sp):
                        for f in os.listdir(sp):
                            if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                        if os.path.exists(raw_p): break
            if os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8", errors="ignore") as f: sample_text = f.read()
                except: pass

        if HAS_ENGINE and self.engine and sample_text:
            score, label = self.engine.calculate_multi_tag_relevance(sample_text, active_tags)
            label_moon = label.replace("🟢", "🌕").replace("🟡", "🌓").replace("🔴", "🌒").replace("⚪", "🌑")
            return chat_path, score, label_moon
        return chat_path, 0, "🌑 0%"

    def update_chat_relevances_only(self):
        """🌟 マルチスレッド並列処理（ThreadPoolExecutor）によるタグスコア一括爆速計算"""
        if not HAS_ENGINE: return
        active_tags = [self.custom_tags[i] for i in self.active_tag_indices if i < len(self.custom_tags)]
        
        chat_paths = []
        for p_item in self.tree_chats.get_children(""):
            for c_item in self.tree_chats.get_children(p_item):
                c_vals = self.tree_chats.item(c_item, "values")
                if c_vals and c_vals[0] == "chat":
                    chat_paths.append(c_vals[1])

        if not chat_paths: return

        # 🌟 CPUの全コアパワーを活用するスレッドプール実行
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._worker_calc_relevance, cp, active_tags) for cp in chat_paths]
            for future in as_completed(futures):
                cp, score, label_moon = future.result()
                self.chat_relevances[cp] = (score, label_moon)

        self.redraw_tree_checks()

    def refresh_chat_tree(self):
        """🌟 元の安定したスキャン構造 ＋ スコア並列計算で100%全ログ表示＆ロード爆速化！"""
        self.tree_chats.delete(*self.tree_chats.get_children())
        active_target_dir = self.custom_external_path if self.is_custom_external_mode else self.save_dir
        if not os.path.exists(active_target_dir): return

        candidates = self.config.get("forge_candidate_chats", [])
        is_filter_candidates = self.var_filter_candidates.get()

        if is_filter_candidates and candidates:
            self.is_custom_external_mode = False
            self.custom_external_path = ""
            self.lbl_ext_path.config(text="")

        active_tags = [self.custom_tags[i] for i in self.active_tag_indices if i < len(self.custom_tags)]
        chat_entries = []
        sub_items = sorted(os.listdir(active_target_dir))

        for sub_name in sub_items:
            sub_path = os.path.join(active_target_dir, sub_name)
            if not os.path.isdir(sub_path): continue
            if sub_name in ["my_documents", "my_forge", "my_RAG_Vault", "branches"]: continue

            child_items = os.listdir(sub_path)
            child_dirs = [c for c in child_items if os.path.isdir(os.path.join(sub_path, c)) and c not in ["assets", "importer", "scraped", "3rd", "branches"]]

            if child_dirs:
                for c_dir in sorted(child_dirs):
                    cp = os.path.join(sub_path, c_dir)
                    chat_entries.append((sub_name, c_dir, cp))
            else:
                chat_entries.append(("📂 参照フォルダ", sub_name, sub_path))

        if not chat_entries:
            direct_mds = [f for f in sub_items if f.endswith(".md")]
            if direct_mds:
                folder_name = os.path.basename(active_target_dir)
                chat_entries.append(("📂 参照フォルダ", folder_name, active_target_dir))

        grouped_chats = {}
        for parent_label, chat_name, chat_path in chat_entries:
            if chat_path in self.excluded_chats: continue
            if is_filter_candidates and candidates and chat_path not in candidates: continue
            grouped_chats.setdefault(parent_label, []).append((chat_name, chat_path))

        # 🌟 チャットパスのリストに対し、マルチスレッド並列処理でスコア計算を一斉実行
        chat_paths_to_calc = [cp for _, _, cp in chat_entries]
        if HAS_ENGINE and chat_paths_to_calc:
            max_workers = min(32, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._worker_calc_relevance, cp, active_tags) for cp in chat_paths_to_calc]
                for future in as_completed(futures):
                    cp, score, label_moon = future.result()
                    self.chat_relevances[cp] = (score, label_moon)

        for p_label, items in grouped_chats.items():
            f_mark = "☑" if self.folder_checks.get(p_label, True) else "☐"
            p_node = self.tree_chats.insert("", "end", text=f"{f_mark} 📁 {p_label}", open=True, values=("folder", p_label))

            for chat_name, chat_path in items:
                _, label_moon = self.chat_relevances.get(chat_path, (0, "🌑 0%"))
                default_chk = True if (candidates and chat_path in candidates) else self.chat_checks.get(chat_path, False)
                self.chat_checks[chat_path] = default_chk

                c_mark = "☑" if default_chk else "☐"
                has_sum = self.find_summary_file_path(chat_path) is not None
                sum_mark = "📝 " if has_sum else "　 "

                self.tree_chats.insert(p_node, "end", text=f"{c_mark} {label_moon} {sum_mark}💬 {chat_name}", values=("chat", chat_path))

        self.refresh_history_listbox()
        self.update_statistics_indicator()
        self.auto_generate_clean_theme_name()

    def on_tree_click(self, event):
        element = self.tree_chats.identify_element(event.x, event.y)
        if element in ["indicator", "space"]: return
        item = self.tree_chats.identify_row(event.y)
        if not item: return

        vals = self.tree_chats.item(item, "values")
        if not vals: return
        item_type = vals[0]
        item_id = vals[1]

        if 20 <= event.x <= 65:
            if item_type == "folder":
                curr = self.folder_checks.get(item_id, True)
                self.folder_checks[item_id] = not curr
                for p_item in self.tree_chats.get_children(""):
                    p_vals = self.tree_chats.item(p_item, "values")
                    if p_vals and p_vals[1] == item_id:
                        for c_item in self.tree_chats.get_children(p_item):
                            c_vals = self.tree_chats.item(c_item, "values")
                            if c_vals and c_vals[0] == "chat":
                                self.chat_checks[c_vals[1]] = not curr
                self.redraw_tree_checks()
            elif item_type == "chat":
                curr = self.chat_checks.get(item_id, False)
                self.chat_checks[item_id] = not curr
                self.redraw_tree_checks()

        if item_type == "chat":
            self.view_target_var.set("raw")
            self.reload_preview_style_for_chat(item_id)

    def reload_preview_style_for_chat(self, chat_path):
        content = ""
        base_dir = chat_path
        if os.path.isfile(chat_path):
            base_dir = os.path.dirname(chat_path)
            try:
                with open(chat_path, "r", encoding="utf-8", errors="ignore") as f: content = f.read()
            except: pass
        else:
            raw_p = os.path.join(chat_path, "raw_master.md")
            if not os.path.exists(raw_p):
                for sk in ["importer", "scraped", "3rd"]:
                    sp = os.path.join(chat_path, sk)
                    if os.path.exists(sp):
                        for f in os.listdir(sp):
                            if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                    if os.path.exists(raw_p): break
            if os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8", errors="ignore") as f: content = f.read()
                except: pass

        if content:
            self.raw_text = content
            self.output_text.config(state="normal")
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert("1.0", content)
            self.reload_preview_style()

    def redraw_tree_checks(self):
        for p_item in self.tree_chats.get_children(""):
            p_vals = self.tree_chats.item(p_item, "values")
            if p_vals and p_vals[0] == "folder":
                s_folder = p_vals[1]
                f_mark = "☑" if self.folder_checks.get(s_folder, True) else "☐"
                self.tree_chats.item(p_item, text=f"{f_mark} 📁 {s_folder}")

                for c_item in self.tree_chats.get_children(p_item):
                    c_vals = self.tree_chats.item(c_item, "values")
                    if c_vals and c_vals[0] == "chat":
                        c_path = c_vals[1]
                        c_mark = "☑" if self.chat_checks.get(c_path, False) else "☐"
                        _, label_moon = self.chat_relevances.get(c_path, (0, "🌑 0%"))
                        has_sum = self.find_summary_file_path(c_path) is not None
                        sum_mark = "📝 " if has_sum else "　 "
                        c_name = os.path.basename(c_path)
                        self.tree_chats.item(c_item, text=f"{c_mark} {label_moon} {sum_mark}💬 {c_name}")

        self.update_statistics_indicator()
        self.auto_generate_clean_theme_name()

    def update_statistics_indicator(self):
        all_displayed = []
        for p_item in self.tree_chats.get_children(""):
            for c_item in self.tree_chats.get_children(p_item):
                c_vals = self.tree_chats.item(c_item, "values")
                if c_vals and c_vals[0] == "chat":
                    all_displayed.append(c_vals[1])

        selected_paths = [cp for cp in all_displayed if self.chat_checks.get(cp, False) and os.path.exists(cp)]
        total_displayed_count = len(all_displayed)
        selected_count = len(selected_paths)
        total_chars_selected = 0
        total_chars_all = 0

        for cp in all_displayed:
            c_len = 0
            if os.path.isfile(cp):
                try: c_len = os.path.getsize(cp)
                except: pass
            else:
                raw_p = os.path.join(cp, "raw_master.md")
                if not os.path.exists(raw_p):
                    for sk in ["importer", "scraped", "3rd"]:
                        sp = os.path.join(cp, sk)
                        if os.path.exists(sp):
                            for f in os.listdir(sp):
                                if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                        if os.path.exists(raw_p): break
                if os.path.exists(raw_p):
                    try: c_len = os.path.getsize(raw_p)
                    except: pass

            total_chars_all += c_len
            if self.chat_checks.get(cp, False):
                total_chars_selected += c_len

        self.lbl_stats_count.config(text=f"・ 表示数: {total_displayed_count} 件 ／ 選択数: {selected_count} 件")
        self.lbl_stats_chars.config(text=f"・ 生ログ文字数: 選択 {total_chars_selected:,} 字 (全体 {total_chars_all:,} 字)")

    def select_all_chats(self):
        for k in self.folder_checks: self.folder_checks[k] = True
        for k in self.chat_checks: self.chat_checks[k] = True
        self.redraw_tree_checks()

    def deselect_all_chats(self):
        for k in self.folder_checks: self.folder_checks[k] = False
        for k in self.chat_checks: self.chat_checks[k] = False
        self.redraw_tree_checks()

    def clear_all_chats(self):
        self.deselect_all_chats()

    def add_chat_manually(self):
        path = filedialog.askdirectory(title="追加するチャットフォルダを選択", initialdir=self.save_dir)
        if path and os.path.isdir(path):
            self.chat_checks[path] = True
            if path in self.excluded_chats:
                self.excluded_chats.remove(path)
            self.refresh_chat_tree()

    def remove_unselected_chats(self):
        for p_item in self.tree_chats.get_children(""):
            for c_item in self.tree_chats.get_children(p_item):
                c_vals = self.tree_chats.item(c_item, "values")
                if c_vals and c_vals[0] == "chat":
                    cp = c_vals[1]
                    if not self.chat_checks.get(cp, False):
                        self.excluded_chats.add(cp)
        self.refresh_chat_tree()

    def collect_selected_texts(self) -> str:
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths and self.raw_text:
            return self.raw_text

        combined = []
        for cp in selected_paths:
            c_name = os.path.basename(cp)
            if os.path.isfile(cp):
                try:
                    with open(cp, "r", encoding="utf-8", errors="ignore") as f:
                        body = f.read()
                    combined.append(f"\n# 📄 File: {c_name}\n---\n" + body)
                except: pass
            else:
                raw_p = os.path.join(cp, "raw_master.md")
                if not os.path.exists(raw_p):
                    for sk in ["importer", "scraped", "3rd"]:
                        sp = os.path.join(cp, sk)
                        if os.path.exists(sp):
                            for f in os.listdir(sp):
                                if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                        if os.path.exists(raw_p): break
                if os.path.exists(raw_p):
                    try:
                        with open(raw_p, "r", encoding="utf-8", errors="ignore") as f:
                            body = f.read()
                        combined.append(f"\n# 📄 File: {c_name}\n---\n" + body)
                    except: pass
        return "\n".join(combined)

    def update_preview_from_engine(self, text, mode="result"):
        self.view_target_var.set(mode)
        self.step_result_cache = text
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)
        self.reload_preview_style()

    def reload_preview_style(self):
        target = self.view_target_var.get()
        if target == "raw":
            content = self.raw_text if self.raw_text else self.collect_selected_texts()
        else:
            content = self.step_result_cache

        if not content:
            content = self.output_text.get("1.0", tk.END).strip()

        if not content: return

        style = self.style_var.get()
        render_rich_markdown(
            text_widget=self.output_text,
            raw_text=content,
            base_dir=self.my_rag_dir,
            show_rich=(style != "none"),
            show_images=self.img_var.get(),
            show_style=style
        )
        active_tags = [self.custom_tags[i] for i in self.active_tag_indices if i < len(self.custom_tags)]
        self.highlight_and_calculate_matches(active_tags)

    def highlight_and_calculate_matches(self, query_words):
        self.output_text.config(state="normal")
        self.output_text.tag_remove("search_highlight", "1.0", tk.END)
        self.output_text.tag_config("search_highlight", background="#fde047", foreground="#000000")
        self.current_match_indices.clear()

        for qw in query_words:
            if not qw: continue
            idx = "1.0"
            while True:
                idx = self.output_text.search(qw, idx, stopindex=tk.END, nocase=True)
                if not idx: break
                end_idx = f"{idx}+{len(qw)}c"
                self.current_match_indices.append(idx)
                self.output_text.tag_add("search_highlight", idx, end_idx)
                idx = end_idx

        self.output_text.config(state="disabled")
        total = len(self.current_match_indices)
        if total > 0:
            self.current_match_pos = 0
            self.jump_to_match_pos(0)
        else:
            self.lbl_nav_count.config(text="[ 0 / 0 件目 ]")

    def jump_to_match_pos(self, pos_idx):
        if not self.current_match_indices: return
        self.current_match_pos = pos_idx % len(self.current_match_indices)
        target_idx = self.current_match_indices[self.current_match_pos]
        self.output_text.see(target_idx)
        total = len(self.current_match_indices)
        self.lbl_nav_count.config(text=f"[ {self.current_match_pos + 1} / {total} 件目 ]")

    def jump_next_match(self):
        if self.current_match_indices: self.jump_to_match_pos(self.current_match_pos + 1)

    def jump_prev_match(self):
        if self.current_match_indices: self.jump_to_match_pos(self.current_match_pos - 1)

    def export_unprocessed_to_external_folder(self):
        """🌟 選択チャットの生データ(Raw)を無加工で外部へコピー保存"""
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            messagebox.showwarning("警告", "対象のチャットを選択してください。")
            return

        target_root_dir = filedialog.askdirectory(title="エクスポート先の外部フォルダを選択してください")
        if not target_root_dir: return

        theme_name = f"Export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        target_export_folder = os.path.join(target_root_dir, theme_name)
        os.makedirs(target_export_folder, exist_ok=True)

        copied_count = 0
        for cp in selected_paths:
            chat_name = os.path.basename(cp)
            if os.path.isfile(cp):
                dst_file = os.path.join(target_export_folder, chat_name)
                try:
                    shutil.copy2(cp, dst_file)
                    copied_count += 1
                except: pass
            else:
                raw_p = os.path.join(cp, "raw_master.md")
                if not os.path.exists(raw_p):
                    for sk in ["importer", "scraped", "3rd"]:
                        sp = os.path.join(cp, sk)
                        if os.path.exists(sp):
                            for f in os.listdir(sp):
                                if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                        if os.path.exists(raw_p): break
                if os.path.exists(raw_p):
                    dst_file = os.path.join(target_export_folder, f"{chat_name}.md")
                    try:
                        shutil.copy2(raw_p, dst_file)
                        copied_count += 1
                    except: pass

        messagebox.showinfo("エクスポート完了", f"【{copied_count} 件】 の元ログを無加工で保存しました。\n保存先: {target_export_folder}")

    def send_raw_to_forge(self):
        """🌟 選択チャット(生データ)を Forge タブへ転送"""
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            messagebox.showwarning("案内", "転送するチャットを選択してください。")
            return
        if self.main_app and hasattr(self.main_app, "switch_to_forge_with_candidates"):
            self.main_app.switch_to_forge_with_candidates(selected_paths)
            messagebox.showinfo("Forge連携", f"【{len(selected_paths)} 件】の生データを Forge へ送信しました！")
        else:
            self.config["forge_candidate_chats"] = selected_paths
            self.save_config_state()
            messagebox.showinfo("送信完了", "チャットパスを選択保持しました。")

    def send_raw_to_compass(self):
        """🌟 選択チャット(生データ)を Compass タブへ転送"""
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            messagebox.showwarning("案内", "転送するチャットを選択してください。")
            return
        if self.main_app and hasattr(self.main_app, "switch_to_compass_with_candidates"):
            self.main_app.switch_to_compass_with_candidates(selected_paths)
            messagebox.showinfo("Compass連携", f"【{len(selected_paths)} 件】の生データを Compass へ送信しました！")

    def save_chronicle_to_vault(self, mode="both", silent=False):
        """🌟 ボタンから呼び出される本番の年表一括保存関数 (モード受取・重複命名ガード対応)"""
        content = self.output_text.get("1.0", tk.END).strip()
        if not content:
            if not silent: messagebox.showwarning("警告", "保存するデータがありません。")
            return None

        theme_name = self.entry_out_filename.get().strip()
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        
        # 🌟 テーマ名のプレフィックス/サフィックス重複を完全に二重防御
        theme_name = re.sub(r'^Chronicle_', '', theme_name, flags=re.IGNORECASE)
        theme_name = re.sub(r'_他\d+件$', '', theme_name)
        if not theme_name:
            theme_name = f"Chronicle_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}"

        theme_name = re.sub(r'[\\/*?:"<>|]', "_", theme_name).strip()
        target_folder = os.path.join(self.entry_out_dir.get().strip(), f"{theme_name}")
        branches_folder = os.path.join(target_folder, "branches")

        saved_files_count = 0

        try:
            # 1. 📜 クロノツリー全景マップ（年表目次）の保存 (both または master モード時)
            if mode in ["both", "master"]:
                os.makedirs(target_folder, exist_ok=True)
                master_file_name = f"raw_Chronicle_{theme_name}.md"
                master_file_path = os.path.join(target_folder, master_file_name)
                with open(master_file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                saved_files_count += 1

            # 2. 📁 個別枝葉ファイルの保存 (both または branches モード時)
            if mode in ["both", "branches"] and HAS_ENGINE and self.engine:
                os.makedirs(branches_folder, exist_ok=True)
                for idx, cp in enumerate(selected_paths, 1):
                    c_name = os.path.basename(cp)
                    if os.path.isfile(cp):
                        try:
                            with open(cp, "r", encoding="utf-8", errors="ignore") as f: raw_c = f.read()
                            compact_c, _ = self.engine.step1_token_compact(raw_c, 5)
                            clean_c, _ = self.engine.step2_cleanse_and_analyze(compact_c, 45)
                            branch_p = os.path.join(branches_folder, f"{idx:02d}_{c_name}")
                            if not branch_p.endswith(".md"): branch_p += ".md"
                            with open(branch_p, "w", encoding="utf-8") as f: f.write(clean_c)
                            saved_files_count += 1
                        except: pass
                    else:
                        raw_p = os.path.join(cp, "raw_master.md")
                        if not os.path.exists(raw_p):
                            for sk in ["importer", "scraped", "3rd"]:
                                sp = os.path.join(cp, sk)
                                if os.path.exists(sp):
                                    for f in os.listdir(sp):
                                        if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                                if os.path.exists(raw_p): break
                        if os.path.exists(raw_p):
                            try:
                                with open(raw_p, "r", encoding="utf-8", errors="ignore") as f: raw_c = f.read()
                                compact_c, _ = self.engine.step1_token_compact(raw_c, 5)
                                clean_c, _ = self.engine.step2_cleanse_and_analyze(compact_c, 45)
                                branch_p = os.path.join(branches_folder, f"{idx:02d}_{c_name}.md")
                                with open(branch_p, "w", encoding="utf-8") as f: f.write(clean_c)
                                saved_files_count += 1
                            except: pass

            if not silent:
                mode_lbl = "全景＋枝葉一括保存" if mode == "both" else ("全景マップのみ保存" if mode == "master" else "個別枝葉のみ保存")
                messagebox.showinfo("保存完了", f"my_RAG_Vault へ一括保存しました！\n\n・保存モード: [{mode_lbl}]\n・出力ファイル/フォルダ: {theme_name}\n・処理件数: {saved_files_count} 件")
            return target_folder
        except Exception as e:
            if not silent: messagebox.showerror("保存エラー", f"ファイル保存に失敗しました:\n{e}")
            return None

    def send_compressed_to_forge(self):
        """🌟 圧縮済みのクロノツリー年表データを Forge タブへ転送"""
        target_folder = self.save_chronicle_to_vault(mode="both", silent=True)
        if target_folder and self.main_app and hasattr(self.main_app, "switch_to_forge_with_candidates"):
            self.main_app.switch_to_forge_with_candidates([target_folder])
            messagebox.showinfo("Forge連携", f"圧縮された年表データを Forge タブへ送信し、切り替えました！")
        else:
            messagebox.showinfo("送信完了", "圧縮年表パスを選択保持しました。")

    def send_compressed_to_compass(self):
        """🌟 圧縮済みのクロノツリー年表データを Compass タブへ転送"""
        target_folder = self.save_chronicle_to_vault(mode="both", silent=True)
        if target_folder and self.main_app and hasattr(self.main_app, "switch_to_compass_with_candidates"):
            self.main_app.switch_to_compass_with_candidates([target_folder])
            messagebox.showinfo("Compass連携", f"圧縮された年表データを Compass タブへ送信し、切り替えました！")


# ================= 🖥️ 単体起動時テストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("📜 AiReChronicleTreeTab - 開発史クロノツリー")
    root.geometry("1200x800")

    app = AiReChronicleTreeFrame(root)
    app.pack(fill="both", expand=True)

    root.mainloop()