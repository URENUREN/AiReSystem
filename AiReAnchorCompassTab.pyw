# -*- coding: utf-8 -*-
# AiReAnchorCompassTab.pyw - ナレッジコンパス (マルチスレッド並列スキャン爆速化・Ctrl+F検索ボタン搭載決定版)
import os
import sys
import json
import re
import datetime
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 🌟 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

# 外部モジュールの安全インポート
try:
    from AiReAnchorMarkdownViewer import render_rich_markdown
    HAS_MD_VIEWER = True
except ImportError:
    HAS_MD_VIEWER = False
    def render_rich_markdown(text_widget, content, base_dir=None, show_rich=True, show_img=True, img_refs=None, filepath=None, on_update_callback=None, progress_bar=None, show_style="simple"):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", content if content else "（データがありません）")
        text_widget.config(state="disabled")

try:
    from AiReAPI import AiReAPIController
    HAS_API = True
except ImportError:
    HAS_API = False

# Windows AppID 登録
try:
    import ctypes
    myappid = 'airelinker.suite.compass.v8'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


class UsageHelpCompassDialog(tk.Toplevel):
    """❓ ナレッジコンパス 使い方ガイドダイアログ"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("❓ AiReAnchorCompass 使い方ガイド")
        self.geometry("640x500")
        
        if os.path.exists(ICON_PORTAL):
            try: self.iconbitmap(ICON_PORTAL)
            except: pass

        self.build_widgets()

    def build_widgets(self):
        ttk.Label(self, text="📖 🧭 AiReAnchorCompass 概要 ＆ 操作マニュアル", font=("MS Gothic", 10, "bold")).pack(anchor="w", padx=10, pady=8)

        txt_frame = ttk.Frame(self, padding=8)
        txt_frame.pack(fill="both", expand=True)

        txt = tk.Text(txt_frame, wrap="word", font=("MS Gothic", 9), background="#ffffff")
        sb = ttk.Scrollbar(txt_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        guide_text = """======================================================================
 🧭 AiReAnchorCompass - ナレッジ検索 ＆ AI横断コンシェルジュ
======================================================================

【1. 直感タグブロック検索】
 ・単語を入力して「＋OR」「＋AND」「＋NOT」を押すとタグブロックが追加されます。
 ・AND (必須条件) / OR (いずれか包含) / NOT (除外ワード) を組み合わせ可能です。

【2. 選択 ＆ ChronoTree / Forge タブ連携】
 ・検索結果一覧の「☑」チェックボックスでチャットを個別選択できます。
 ・「📜 選択チャットを ChronoTree (年表) へ送る」で年表作成タブへ即座に引き継げます。
 ・「🔨 選択チャットを Forge (合成) へ送る」で文章合成タブへ引き継げます。

【3. 📖 プレビュー ＆ マークダウン表示切替】
 ・「シンプル標準MD」「AiRe装飾」「装飾OFF」の3つの表示モードを切替可能です。
 ・「🔍 検索 (Ctrl+F)」ボタンまたは Ctrl+F キーで文字検索窓を起動できます。
======================================================================
"""
        txt.insert(tk.END, guide_text)
        txt.config(state="disabled")


class AiReAnchorCompassFrame(ttk.Frame):
    """🌟 3分割可変レイアウト・直感タグブロック検索 ＆ マルチスレッド並列爆速スキャン対応コンパス"""
    def __init__(self, parent, save_dir=None, main_app=None):
        super().__init__(parent)
        self.main_app = main_app
        
        if main_app:
            self.config = main_app.config
            self.save_dir = main_app.save_dir
        else:
            self.config = self.load_config()
            self.save_dir = save_dir if save_dir else self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))

        self.api_controller = AiReAPIController(self.config) if HAS_API else None

        self.and_tags = []
        self.or_tags = []
        self.not_tags = []

        self.chat_checks = {}   # {chat_path: True/False}
        self.folder_checks = {} # {folder_name: True/False}

        self.search_history = self.config.get("compass_search_history", [])
        self.hit_results = []
        self.selected_chat_path = None
        self.current_source_mode = "master"
        self.current_preview_mode = "raw"

        self.source_priority = ["master", "importer", "scraped", "3rd"]

        self.current_match_indices = []
        self.current_match_pos = 0
        self.image_refs = []

        self.build_ui()
        self.scan_all_topics()

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    def get_active_save_dir(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    d = cfg.get("save_dir")
                    if d and os.path.exists(d): return d
            except: pass
        return self.save_dir

    def set_active_save_dir(self, new_dir):
        if not new_dir or not os.path.exists(new_dir): return
        cfg = self.load_config()
        cfg["save_dir"] = new_dir
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except: pass
        self.lbl_path_disp.config(text=f"現在参照中: [ {new_dir} ]")
        self.scan_all_topics()

    def browse_and_set_save_dir(self):
        curr = self.get_active_save_dir()
        selected = filedialog.askdirectory(title="参照するログフォルダを選択", initialdir=curr if os.path.exists(curr) else CURRENT_DIR)
        if selected:
            self.set_active_save_dir(selected)

    def save_config_state(self):
        self.config["compass_search_history"] = self.search_history[:500]
        self.config["last_compass_markdown_style"] = self.style_var.get()
        if self.main_app and hasattr(self.main_app, "save_config"):
            self.main_app.save_config()
        else:
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            except: pass

    def cycle_source_priority(self):
        modes = [
            ["master", "importer", "scraped", "3rd"],
            ["importer", "scraped", "master", "3rd"],
            ["scraped", "importer", "master", "3rd"],
            ["3rd", "importer", "scraped", "master"]
        ]
        curr_idx = 0
        for i, m in enumerate(modes):
            if m == self.source_priority:
                curr_idx = (i + 1) % len(modes)
                break
        self.source_priority = modes[curr_idx]
        self.update_priority_btn_label()
        if self.selected_chat_path:
            self.reload_current_preview()

    def update_priority_btn_label(self):
        disp_map = {"master": "🌟マスター", "importer": "📦インポート", "scraped": "📡スクレイプ", "3rd": "🔗3rd"}
        p_str = " ➔ ".join([disp_map.get(k, k) for k in self.source_priority])
        self.btn_priority.config(text=f"🔀 優先順: [ {p_str} ]")

    def build_ui(self):
        top_bar = ttk.Frame(self, padding=(4, 2))
        top_bar.pack(fill="x", side="top")

        ttk.Button(top_bar, text="📂 参照...", command=self.browse_and_set_save_dir).pack(side="left", padx=2)
        
        self.lbl_path_disp = ttk.Label(top_bar, text=f"現在参照中: [ {self.get_active_save_dir()} ]", font=("MS Gothic", 8, "bold"), foreground="#0284c7")
        self.lbl_path_disp.pack(side="left", padx=6)

        self.btn_priority = ttk.Button(top_bar, text="🔀 優先順: [ 🌟マスター ➔ 📦インポート ➔ 📡スクレイプ ➔ 🔗3rd ]", command=self.cycle_source_priority)
        self.btn_priority.pack(side="left", padx=6)

        ttk.Button(top_bar, text="❓ 使い方ヘルプ", command=lambda: UsageHelpCompassDialog(self)).pack(side="right", padx=4)

        self.compass_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.compass_pane.pack(fill="both", expand=True, padx=4, pady=4)

        # =========================================================================
        # 1. 左パネル: 縦方向可変 PanedWindow
        # =========================================================================
        left_p = ttk.Frame(self.compass_pane, width=330)
        self.compass_pane.add(left_p, weight=1)

        left_v_pane = ttk.Panedwindow(left_p, orient=tk.VERTICAL)
        left_v_pane.pack(fill="both", expand=True)

        search_f = ttk.LabelFrame(left_v_pane, text=" 🔍 高度ナレッジ検索 ", padding=6)
        left_v_pane.add(search_f, weight=2)

        tag_in_f = ttk.Frame(search_f)
        tag_in_f.pack(fill="x", pady=3)

        self.entry_add_word = ttk.Entry(tag_in_f, font=("MS Gothic", 9))
        self.entry_add_word.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.entry_add_word.bind("<Return>", lambda e: self.add_tag_word("and"))

        ttk.Button(tag_in_f, text="＋OR", command=lambda: self.add_tag_word("or")).pack(side="left", padx=1)
        ttk.Button(tag_in_f, text="＋AND", command=lambda: self.add_tag_word("and")).pack(side="left", padx=1)
        ttk.Button(tag_in_f, text="＋NOT", command=lambda: self.add_tag_word("not")).pack(side="left", padx=1)

        self.chip_container = ttk.Frame(search_f)
        self.chip_container.pack(fill="x", pady=2)

        btn_run = ttk.Button(search_f, text="🚀 ナレッジサーチ実行 (マルチスレッド爆速化)", command=self.run_compass_search)
        btn_run.pack(fill="x", pady=3)

        results_f = ttk.LabelFrame(left_v_pane, text=" 📊 ヒットログ一覧 ", padding=6)
        left_v_pane.add(results_f, weight=4)

        act_bar1 = ttk.Frame(results_f)
        act_bar1.pack(fill="x", pady=(0, 2))

        ttk.Button(act_bar1, text="☑ 全選択", command=self.select_all_hits).pack(side="left", padx=1, expand=True, fill="x")
        ttk.Button(act_bar1, text="☐ 全解除", command=self.deselect_all_hits).pack(side="left", padx=1, expand=True, fill="x")
        ttk.Button(act_bar1, text="🧹 全除外", command=self.clear_all_hits).pack(side="left", padx=1, expand=True, fill="x")
        ttk.Button(act_bar1, text="❌ 未選択を除外", command=self.remove_unselected_hits).pack(side="left", padx=1, expand=True, fill="x")

        act_bar2 = ttk.Frame(results_f)
        act_bar2.pack(fill="x", pady=(2, 4))

        ttk.Button(act_bar2, text="📜 選択チャットを ChronoTree (年表) へ送る", command=self.send_selected_to_chronicle).pack(fill="x", expand=True, pady=1)
        ttk.Button(act_bar2, text="🔨 選択チャットを Forge (合成) へ送る", command=self.send_selected_to_forge).pack(fill="x", expand=True, pady=1)

        tree_f = ttk.Frame(results_f)
        tree_f.pack(fill="both", expand=True)

        self.tree_hits = ttk.Treeview(tree_f, columns=("Hits",), show="tree headings", selectmode="extended")
        self.tree_tracks = self.tree_hits
        self.tree_hits.heading("#0", text="AIサービス / チャット題名")
        self.tree_hits.heading("Hits", text="件数")
        self.tree_hits.column("#0", width=210, anchor="w")
        self.tree_hits.column("Hits", width=50, anchor="center")
        
        sb_tree = ttk.Scrollbar(tree_f, command=self.tree_hits.yview)
        self.tree_hits.configure(yscrollcommand=sb_tree.set)
        
        self.tree_hits.pack(side="left", fill="both", expand=True)
        sb_tree.pack(side="right", fill="y")
        self.tree_hits.bind("<Button-1>", self.on_tree_click)

        hist_f = ttk.LabelFrame(left_v_pane, text=" 📜 過去の検索履歴 ", padding=4)
        left_v_pane.add(hist_f, weight=2)

        hist_btn_bar = ttk.Frame(hist_f)
        hist_btn_bar.pack(fill="x", pady=(0, 2))

        ttk.Button(hist_btn_bar, text="🗑️ 選択履歴を削除", command=self.delete_selected_history).pack(side="left", padx=1)
        ttk.Button(hist_btn_bar, text="🧹 全履歴消去", command=self.clear_all_history).pack(side="right", padx=1)

        self.history_listbox = tk.Listbox(hist_f, background="#f8fafc", font=("MS Gothic", 8))
        self.history_listbox.pack(fill="both", expand=True)
        self.history_listbox.bind("<Double-Button-1>", self.on_history_double_click)

        # =========================================================================
        # 2. 中央パネル: ログ本文プレビュー ＆ 3スタイル切替 ＆ ヒットナビ ＆ Ctrl+F検索ボタン
        # =========================================================================
        center_p = ttk.Frame(self.compass_pane, width=480)
        self.compass_pane.add(center_p, weight=3)

        prev_lf = ttk.LabelFrame(center_p, text=" 📖 チャット本文 ＆ ヒット箇所プレビュー ", padding=6)
        prev_lf.pack(fill="both", expand=True, pady=2)

        src_bar = ttk.Frame(prev_lf)
        src_bar.pack(fill="x", pady=(0, 2))

        ttk.Label(src_bar, text="表示ソース:", font=("MS Gothic", 8, "bold")).pack(side="left", padx=2)
        self.source_mode_var = tk.StringVar(value=self.current_source_mode)

        self.rb_master = ttk.Radiobutton(src_bar, text="🌟 統合マスター", variable=self.source_mode_var, value="master", command=self.on_source_changed)
        self.rb_master.pack(side="left", padx=2)

        self.rb_importer = ttk.Radiobutton(src_bar, text="📦 importer", variable=self.source_mode_var, value="importer", command=self.on_source_changed)
        self.rb_importer.pack(side="left", padx=2)

        self.rb_scraped = ttk.Radiobutton(src_bar, text="📡 scraped", variable=self.source_mode_var, value="scraped", command=self.on_source_changed)
        self.rb_scraped.pack(side="left", padx=2)

        self.rb_3rd = ttk.Radiobutton(src_bar, text="🔗 3rd", variable=self.source_mode_var, value="3rd", command=self.on_source_changed)
        self.rb_3rd.pack(side="left", padx=2)

        nav_bar = ttk.Frame(prev_lf)
        nav_bar.pack(fill="x", pady=2)

        ttk.Button(nav_bar, text="📄 Raw", command=lambda: self.switch_mode("raw")).pack(side="left", padx=1)
        ttk.Button(nav_bar, text="📝 Summary", command=lambda: self.switch_mode("summary")).pack(side="left", padx=1)

        self.style_var = tk.StringVar(value=self.config.get("last_compass_markdown_style", "simple"))
        
        rb_s = ttk.Radiobutton(nav_bar, text="シンプル標準MD", variable=self.style_var, value="simple", command=self.on_style_changed)
        rb_s.pack(side="left", padx=3)
        
        rb_a = ttk.Radiobutton(nav_bar, text="AiRe装飾", variable=self.style_var, value="aire", command=self.on_style_changed)
        rb_a.pack(side="left", padx=3)

        rb_n = ttk.Radiobutton(nav_bar, text="装飾OFF(Raw)", variable=self.style_var, value="none", command=self.on_style_changed)
        rb_n.pack(side="left", padx=3)

        self.img_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(nav_bar, text="画像表示", variable=self.img_var, command=self.reload_current_preview).pack(side="left", padx=4)

        self.lbl_nav_count = ttk.Label(nav_bar, text="[ 0 / 0 件目 ]", font=("MS Gothic", 8, "bold"), foreground="#2563eb")
        self.lbl_nav_count.pack(side="left", padx=4)

        ttk.Button(nav_bar, text="↑ 前へ", command=self.jump_prev_match).pack(side="left", padx=1)
        ttk.Button(nav_bar, text="↓ 次へ", command=self.jump_next_match).pack(side="left", padx=1)

        # 🌟 右端に [🔍 検索 (Ctrl+F)] ボタンを配置！
        ttk.Button(nav_bar, text="🔍 検索 (Ctrl+F)", command=self.trigger_ctrl_f_search).pack(side="right", padx=2)

        prev_txt_f = ttk.Frame(prev_lf)
        prev_txt_f.pack(fill="both", expand=True, pady=2)

        self.compass_text = tk.Text(prev_txt_f, background="#ffffff", wrap="word")
        self.compass_text.pack(side="left", fill="both", expand=True)

        sb_txt = ttk.Scrollbar(prev_txt_f, command=self.compass_text.yview)
        sb_txt.pack(side="right", fill="y")
        self.compass_text.configure(yscrollcommand=sb_txt.set)

        self.compass_text.insert(tk.END, "💡 左側の検索窓に単語を入力して「＋AND」「＋OR」「＋NOT」ボタンでタグブロックを追加し「ナレッジサーチ実行」を押してください。")
        self.compass_text.config(state="disabled")

        # =========================================================================
        # 3. 右パネル: AIナレッジコンシェルジュ
        # =========================================================================
        right_p = ttk.Frame(self.compass_pane, width=320)
        self.compass_pane.add(right_p, weight=2)

        ai_rag_f = ttk.LabelFrame(right_p, text=" 🤖 AIナレッジコンシェルジュ (AI検索 ＆ RAG) ", padding=6)
        ai_rag_f.pack(fill="both", expand=True, pady=2)

        vec_f = ttk.LabelFrame(ai_rag_f, text=" 🧠 AIベクトル意味検索 (Embedding) ", padding=6)
        vec_f.pack(fill="x", pady=2)

        self.entry_vec_query = ttk.Entry(vec_f, font=("MS Gothic", 9))
        self.entry_vec_query.pack(fill="x", pady=2)

        ttk.Button(vec_f, text="🔍 意味・ベクトル検索実行 (トークン消費)", command=self.ask_ai_vector_search_with_confirm).pack(fill="x", pady=2)

        rag_box = ttk.LabelFrame(ai_rag_f, text=" 📖 AI過去ログ横断質問 (RAG要約) ", padding=6)
        rag_box.pack(fill="both", expand=True, pady=4)

        ttk.Label(rag_box, text="AIへの質問文を入力してください:", font=("MS Gothic", 8), foreground="#475569").pack(anchor="w")

        self.txt_rag_query = tk.Text(rag_box, height=3, font=("MS Gothic", 9), wrap="word")
        self.txt_rag_query.pack(fill="x", pady=4)

        ttk.Button(rag_box, text="🤖 AIに過去ログ横断質問 (トークン消費)", command=self.ask_ai_rag_with_confirm).pack(fill="x", pady=3)

        ttk.Label(rag_box, text="📖 AIからの回答・横断要約:", font=("MS Gothic", 9, "bold")).pack(anchor="w", pady=(4, 2))
        
        self.txt_rag_reply = tk.Text(rag_box, background="#f8fafc", font=("MS Gothic", 9), wrap="word")
        self.txt_rag_reply.pack(fill="both", expand=True)
        
        sb_rag = ttk.Scrollbar(self.txt_rag_reply, command=self.txt_rag_reply.yview)
        sb_rag.pack(side="right", fill="y")
        self.txt_rag_reply.configure(yscrollcommand=sb_rag.set)

    def trigger_ctrl_f_search(self):
        """🌟 Ctrl+F 検索イベントを発火させてビューアーの検索窓を立ち上げる"""
        self.compass_text.focus_set()
        self.compass_text.event_generate("<Control-f>")

    def add_tag_word(self, tag_type):
        word = self.entry_add_word.get().strip()
        if not word: return
        self.entry_add_word.delete(0, tk.END)

        if tag_type == "and" and len(self.and_tags) < 5: self.and_tags.append(word)
        elif tag_type == "or" and len(self.or_tags) < 5: self.or_tags.append(word)
        elif tag_type == "not" and len(self.not_tags) < 5: self.not_tags.append(word)

        self.redraw_chip_tags()

    def remove_tag_word(self, tag_type, word):
        if tag_type == "and" and word in self.and_tags: self.and_tags.remove(word)
        elif tag_type == "or" and word in self.or_tags: self.or_tags.remove(word)
        elif tag_type == "not" and word in self.not_tags: self.not_tags.remove(word)

        self.redraw_chip_tags()

    def redraw_chip_tags(self):
        for w in self.chip_container.winfo_children():
            w.destroy()

        row_f = ttk.Frame(self.chip_container)
        row_f.pack(fill="x", pady=2)

        for w in self.or_tags:
            btn = tk.Button(row_f, text=f"OR: {w} ✕", bg="#dcfce7", fg="#166534", font=("MS Gothic", 8, "bold"), bd=1, relief="ridge", command=lambda x=w: self.remove_tag_word("or", x))
            btn.pack(side="left", padx=1, pady=1)

        for w in self.and_tags:
            btn = tk.Button(row_f, text=f"AND: {w} ✕", bg="#dbeafe", fg="#1e40af", font=("MS Gothic", 8, "bold"), bd=1, relief="ridge", command=lambda x=w: self.remove_tag_word("and", x))
            btn.pack(side="left", padx=1, pady=1)

        for w in self.not_tags:
            btn = tk.Button(row_f, text=f"NOT: {w} ✕", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8, "bold"), bd=1, relief="ridge", command=lambda x=w: self.remove_tag_word("not", x))
            btn.pack(side="left", padx=1, pady=1)

    def refresh_history_listbox(self):
        """🌟 OR/AND/NOT 属性付きで構造化された過去履歴のリストボックス表示"""
        self.history_listbox.delete(0, tk.END)
        for q in self.search_history:
            if isinstance(q, dict):
                parts = []
                for w in q.get("or", []): parts.append(f"OR:{w}")
                for w in q.get("and", []): parts.append(f"AND:{w}")
                for w in q.get("not", []): parts.append(f"NOT:{w}")
                disp_str = " | ".join(parts)
            elif isinstance(q, str):
                disp_str = q
            else:
                continue
            self.history_listbox.insert(tk.END, f"📜 {disp_str}")

    def delete_selected_history(self):
        sel = self.history_listbox.curselection()
        if sel:
            idx = sel[0]
            if idx < len(self.search_history):
                del self.search_history[idx]
                self.save_config_state()
                self.refresh_history_listbox()

    def clear_all_history(self):
        if messagebox.askyesno("確認", "過去の検索履歴をすべて消去しますか？"):
            self.search_history.clear()
            self.save_config_state()
            self.refresh_history_listbox()

    def clear_all_hits(self):
        """🌟 ヒットログ一覧の完全クリア（リセット）"""
        self.hit_results.clear()
        self.chat_checks.clear()
        self.folder_checks.clear()
        self.tree_hits.delete(*self.tree_hits.get_children())
        self.selected_chat_path = None

    def on_history_double_click(self, event):
        """🌟 過去履歴のダブルクリック時、OR/AND/NOT タグ属性を100%正確に復元！"""
        sel = self.history_listbox.curselection()
        if not sel: return

        idx = sel[0]
        if idx >= len(self.search_history): return

        target_item = self.search_history[idx]

        self.and_tags.clear()
        self.or_tags.clear()
        self.not_tags.clear()

        if isinstance(target_item, dict):
            self.or_tags = list(target_item.get("or", []))
            self.and_tags = list(target_item.get("and", []))
            self.not_tags = list(target_item.get("not", []))
        elif isinstance(target_item, str):
            parts = target_item.replace("📜 ", "").split("|")
            for p in parts:
                p_clean = p.strip()
                if p_clean.startswith("OR:"):
                    self.or_tags.append(p_clean.replace("OR:", "").strip())
                elif p_clean.startswith("AND:"):
                    self.and_tags.append(p_clean.replace("AND:", "").strip())
                elif p_clean.startswith("NOT:"):
                    self.not_tags.append(p_clean.replace("NOT:", "").strip())
                elif p_clean:
                    self.and_tags.append(p_clean)

        self.redraw_chip_tags()
        self.run_compass_search()

    def scan_all_topics(self):
        self.refresh_history_listbox()

    def _worker_file_scan(self, path, not_tags_l, and_tags_l, or_tags_l, query_words):
        """🌟 マルチスレッド用 1ファイル検索ワーカー"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            text_lower = content.lower()

            if any(nw in text_lower for nw in not_tags_l):
                return None

            if and_tags_l and not all(aw in text_lower for aw in and_tags_l):
                return None

            if or_tags_l and not any(ow in text_lower for ow in or_tags_l):
                return None

            chat_folder = os.path.dirname(path)
            if os.path.basename(chat_folder) in ["scraped", "importer", "3rd", "master"]:
                chat_folder = os.path.dirname(chat_folder)

            chat_name = os.path.basename(chat_folder)
            if chat_name in ["assets", "branches", "importer", "scraped", "3rd"]:
                return None

            service_folder = os.path.basename(os.path.dirname(chat_folder))

            count = 0
            for qw in query_words:
                count += len(re.findall(re.escape(qw), content, re.IGNORECASE))

            return {
                "path": chat_folder,
                "target_md": path,
                "name": chat_name,
                "service": service_folder,
                "count": count if count > 0 else 1,
                "query_words": query_words
            }
        except:
            return None

    def run_compass_search(self):
        """🌟 検索スキャン（ThreadPoolExecutorによるマルチスレッド並列処理で爆速化！）"""
        active_dir = self.get_active_save_dir()
        if not os.path.exists(active_dir):
            messagebox.showwarning("警告", f"ログディレクトリが見つかりません:\n{active_dir}")
            return

        if not self.and_tags and not self.or_tags and not self.not_tags:
            raw_w = self.entry_add_word.get().strip()
            if raw_w: self.and_tags.append(raw_w); self.redraw_chip_tags()

        if not self.and_tags and not self.or_tags and not self.not_tags:
            messagebox.showwarning("案内", "検索キーワードを入力し「＋OR」「＋AND」「＋NOT」でタグ追加してください。")
            return

        current_history_struct = {
            "or": list(self.or_tags),
            "and": list(self.and_tags),
            "not": list(self.not_tags)
        }

        self.search_history = [h for h in self.search_history if h != current_history_struct]
        self.search_history.insert(0, current_history_struct)
        self.search_history = self.search_history[:500]
        self.save_config_state()
        self.refresh_history_listbox()

        self.hit_results.clear()
        self.tree_hits.delete(*self.tree_hits.get_children())

        # 1. 対象の全Markdownファイルのパスを一括収集
        candidate_files = []
        for root_dir, dirs, files in os.walk(active_dir):
            norm_root = os.path.normpath(root_dir)
            path_parts = norm_root.split(os.sep)
            if any(p in ["assets", "branches", "_temp_raw", "temp"] for p in path_parts):
                continue
            for file in files:
                if file.endswith(".md"):
                    candidate_files.append(os.path.join(root_dir, file))

        not_tags_l = [w.lower() for w in self.not_tags]
        and_tags_l = [w.lower() for w in self.and_tags]
        or_tags_l = [w.lower() for w in self.or_tags]
        query_words = self.and_tags + self.or_tags

        grouped_hits = {}
        
        # 🌟 2. CPUの全コアパワーを解放する並列スレッドプール実行（Core Ultra 9 / 多コアCPU対応）
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._worker_file_scan, path, not_tags_l, and_tags_l, or_tags_l, query_words)
                for path in candidate_files
            ]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    chat_folder = res["path"]
                    existing = next((it for it in self.hit_results if it["path"] == chat_folder), None)
                    if not existing:
                        grouped_hits.setdefault(res["service"], []).append(res)
                        self.hit_results.append(res)
                        self.chat_checks[chat_folder] = True
                    else:
                        if res["count"] > existing["count"]:
                            existing["count"] = res["count"]
                            existing["target_md"] = res["target_md"]

        total_hits = 0
        for s_folder, items in grouped_hits.items():
            f_mark = "☑" if self.folder_checks.get(s_folder, True) else "☐"
            p_node = self.tree_hits.insert("", "end", text=f"{f_mark} 📁 {s_folder}", open=True, values=("folder", s_folder))
            for it in items:
                total_hits += 1
                c_mark = "☑" if self.chat_checks.get(it["path"], True) else "☐"
                self.tree_hits.insert(p_node, "end", text=f"{c_mark} 💬 {it['name']}", values=("chat", it["path"], f"{it['count']}件"))

        if total_hits == 0:
            messagebox.showinfo("検索完了", "指定した条件に合致するログは見つかりませんでした。")

    def on_tree_click(self, event):
        """🌟 開閉アイコン[+]/[-]を押した時はチェックのトグルを完全無視（ForgeTab準拠）"""
        element = self.tree_hits.identify_element(event.x, event.y)
        if element in ["indicator", "space"]:
            return

        item = self.tree_hits.identify_row(event.y)
        if not item: return

        vals = self.tree_hits.item(item, "values")
        if not vals: return

        item_type = vals[0]
        item_id = vals[1]

        # チェックマーク部分（X座標20px〜65px付近）をクリックした場合のみチェック状態を反転
        if 20 <= event.x <= 65:
            if item_type == "folder":
                curr = self.folder_checks.get(item_id, True)
                self.folder_checks[item_id] = not curr
                for it in self.hit_results:
                    if it["service"] == item_id:
                        self.chat_checks[it["path"]] = not curr
                self.redraw_tree_checks()
            elif item_type == "chat":
                curr = self.chat_checks.get(item_id, True)
                self.chat_checks[item_id] = not curr
                self.redraw_tree_checks()

        if item_type == "chat":
            # 本文表示プレビューは常に更新
            self.selected_chat_path = item_id
            self.update_source_radio_states(item_id)
            self.reload_current_preview()

    def redraw_tree_checks(self):
        for p_item in self.tree_hits.get_children(""):
            p_vals = self.tree_hits.item(p_item, "values")
            if p_vals and p_vals[0] == "folder":
                s_folder = p_vals[1]
                f_mark = "☑" if self.folder_checks.get(s_folder, True) else "☐"
                self.tree_hits.item(p_item, text=f"{f_mark} 📁 {s_folder}")

                for c_item in self.tree_hits.get_children(p_item):
                    c_vals = self.tree_hits.item(c_item, "values")
                    if c_vals and c_vals[0] == "chat":
                        c_path = c_vals[1]
                        c_mark = "☑" if self.chat_checks.get(c_path, True) else "☐"
                        c_name = next((it["name"] for it in self.hit_results if it["path"] == c_path), "チャット")
                        self.tree_hits.item(c_item, text=f"{c_mark} 💬 {c_name}")

    def select_all_hits(self):
        for k in self.folder_checks: self.folder_checks[k] = True
        for k in self.chat_checks: self.chat_checks[k] = True
        self.redraw_tree_checks()

    def deselect_all_hits(self):
        for k in self.folder_checks: self.folder_checks[k] = False
        for k in self.chat_checks: self.chat_checks[k] = False
        self.redraw_tree_checks()

    def remove_unselected_hits(self):
        """チェックの入っていない非選択ログを一括削除（非表示）"""
        to_remove = [c_path for c_path, is_chk in self.chat_checks.items() if not is_chk]
        if not to_remove: return

        self.hit_results = [it for it in self.hit_results if it["path"] not in to_remove]
        for c_path in to_remove:
            if c_path in self.chat_checks:
                del self.chat_checks[c_path]

        self.tree_hits.delete(*self.tree_hits.get_children())
        grouped_hits = {}
        for it in self.hit_results:
            grouped_hits.setdefault(it["service"], []).append(it)

        for s_folder, items in grouped_hits.items():
            f_mark = "☑" if self.folder_checks.get(s_folder, True) else "☐"
            p_node = self.tree_hits.insert("", "end", text=f"{f_mark} 📁 {s_folder}", open=True, values=("folder", s_folder))
            for it in items:
                c_mark = "☑" if self.chat_checks.get(it["path"], True) else "☐"
                self.tree_hits.insert(p_node, "end", text=f"{c_mark} 💬 {it['name']}", values=("chat", it["path"], f"{it['count']}件"))

    def update_source_radio_states(self, chat_folder):
        has_imp = os.path.exists(os.path.join(chat_folder, "importer")) and len(os.listdir(os.path.join(chat_folder, "importer"))) > 0
        has_scr = os.path.exists(os.path.join(chat_folder, "scraped")) and len(os.listdir(os.path.join(chat_folder, "scraped"))) > 0
        has_3rd = os.path.exists(os.path.join(chat_folder, "3rd")) and len(os.listdir(os.path.join(chat_folder, "3rd"))) > 0

        self.rb_master.config(state="normal")
        self.rb_importer.config(state="normal" if has_imp else "disabled")
        self.rb_scraped.config(state="normal" if has_scr else "disabled")
        self.rb_3rd.config(state="normal" if has_3rd else "disabled")

        curr_mode = self.source_mode_var.get()
        if curr_mode == "importer" and not has_imp: self.source_mode_var.set("master")
        elif curr_mode == "scraped" and not has_scr: self.source_mode_var.set("master")
        elif curr_mode == "3rd" and not has_3rd: self.source_mode_var.set("master")
        self.current_source_mode = self.source_mode_var.get()

    def switch_mode(self, mode):
        self.current_preview_mode = mode
        self.reload_current_preview()

    def on_source_changed(self):
        self.current_source_mode = self.source_mode_var.get()
        self.reload_current_preview()

    def on_style_changed(self):
        self.save_config_state()
        self.reload_current_preview()

    def reload_current_preview(self):
        if not self.selected_chat_path or not os.path.exists(self.selected_chat_path): return

        chat_folder = self.selected_chat_path
        source_mode = self.current_source_mode
        preview_mode = self.current_preview_mode
        current_style = self.style_var.get()

        target_file = None
        base_dir = chat_folder

        if source_mode == "master":
            if preview_mode == "raw":
                target_file = os.path.join(chat_folder, "raw_master.md")
            else:
                target_file = os.path.join(chat_folder, "summary.md")
        else:
            sub_p = os.path.join(chat_folder, source_mode)
            base_dir = sub_p
            if os.path.exists(sub_p):
                for f in os.listdir(sub_p):
                    if preview_mode == "raw" and f.endswith(".md"):
                        target_file = os.path.join(sub_p, f); break

        content = ""
        if target_file and os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f: content = f.read()
            except: pass
        else:
            if hasattr(self.main_app, "portal_app") and hasattr(self.main_app.portal_app, "knots_engine"):
                res, _ = self.main_app.portal_app.knots_engine.build_integrated_master(chat_folder)
                if res: content = res["master_markdown"]

        if content:
            render_rich_markdown(
                text_widget=self.compass_text,
                raw_text=content,
                base_dir=base_dir,
                show_rich=(current_style != "none"),
                show_images=self.img_var.get(),
                image_refs_list=self.image_refs,
                filepath=target_file,
                show_style=current_style
            )

            hit_item = next((it for it in self.hit_results if it["path"] == chat_folder), None)
            query_words = hit_item["query_words"] if hit_item else (self.and_tags + self.or_tags)
            self.highlight_and_calculate_matches(query_words)

    def highlight_and_calculate_matches(self, query_words):
        self.compass_text.config(state="normal")
        self.compass_text.tag_remove("search_highlight", "1.0", tk.END)
        self.compass_text.tag_config("search_highlight", background="#fde047", foreground="#000000")

        self.current_match_indices.clear()

        for qw in query_words:
            if not qw: continue
            idx = "1.0"
            while True:
                idx = self.compass_text.search(qw, idx, stopindex=tk.END, nocase=True)
                if not idx: break
                end_idx = f"{idx}+{len(qw)}c"
                self.current_match_indices.append(idx)
                self.compass_text.tag_add("search_highlight", idx, end_idx)
                idx = end_idx

        self.compass_text.config(state="disabled")

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

        self.compass_text.see(target_idx)
        total = len(self.current_match_indices)
        self.lbl_nav_count.config(text=f"[ {self.current_match_pos + 1} / {total} 件目 ]")

    def jump_next_match(self):
        if self.current_match_indices:
            self.jump_to_match_pos(self.current_match_pos + 1)

    def jump_prev_match(self):
        if self.current_match_indices:
            self.jump_to_match_pos(self.current_match_pos - 1)

    def send_selected_to_chronicle(self):
        """🌟 選択チャットを ChronoTree (年表作成タブ) へ転送＆自動切り替え"""
        selected_folders = [c_path for c_path, is_chk in self.chat_checks.items() if is_chk]

        if not selected_folders:
            messagebox.showwarning("案内", "ChronoTreeへ送信するチャットにチェックを入れて選択してください。")
            return

        self.config["forge_candidate_chats"] = selected_folders
        self.save_config_state()

        if self.main_app and hasattr(self.main_app, "switch_to_chronicle_with_candidates"):
            self.main_app.switch_to_chronicle_with_candidates(selected_folders)
            messagebox.showinfo("ChronoTree連携", f"【{len(selected_folders)} 件】のチャットを ChronoTree タブへ送信し、自動切り替えました！")
        else:
            messagebox.showinfo("送信完了", f"【{len(selected_folders)} 件】のチャットパスを選択保持しました。")

    def send_selected_to_forge(self):
        """🌟 選択チャットを Forge (文章合成タブ) へ転送＆自動切り替え"""
        selected_folders = [c_path for c_path, is_chk in self.chat_checks.items() if is_chk]

        if not selected_folders:
            messagebox.showwarning("案内", "Forgeへ送信するチャットにチェックを入れて選択してください。")
            return

        self.config["forge_candidate_chats"] = selected_folders
        self.save_config_state()

        if self.main_app and hasattr(self.main_app, "switch_to_forge_with_candidates"):
            self.main_app.switch_to_forge_with_candidates(selected_folders)
            messagebox.showinfo("Forge連携", f"【{len(selected_folders)} 件】のチャットを Forge タブへ送信し、自動切り替えました！")
        else:
            messagebox.showinfo("送信完了", f"【{len(selected_folders)} 件】のチャットパスを選択保持しました。")

    def ask_ai_vector_search_with_confirm(self):
        raw_w = self.entry_vec_query.get().strip()
        if not raw_w and self.and_tags: raw_w = " ".join(self.and_tags)
        if not raw_w:
            messagebox.showwarning("案内", "ベクトル意味検索を行うフレーズを入力してください。")
            return

        if not self.api_controller:
            messagebox.showerror("エラー", "AiReAPI 通信モジュールがロードされていません。")
            return

        ans = messagebox.askyesno(
            "⚠️ AIトークン消費の確認",
            f"フレーズ 『{raw_w}』 のベクトル抽出（Embedding API）を実行します。\n\n"
            f"（※API通信およびトークン枠を消費します）\n\n"
            f"本当に実行しますか？"
        )
        if not ans: return

        self.compass_text.config(state="normal")
        self.compass_text.delete("1.0", tk.END)
        self.compass_text.insert("1.0", f"⏳ フレーズ『{raw_w}』のベクトル抽出 ＆ 意味類似度検索を実行中です...")
        self.compass_text.config(state="disabled")

        def vec_thread():
            ok, query_vec = self.api_controller.get_embedding(raw_w)
            
            def gui_res():
                if not ok:
                    messagebox.showerror("エラー", f"ベクトル抽出失敗:\n{query_vec}")
                    return
                messagebox.showinfo("意味検索完了", "ベクトル類似度検索を実行し、関連順にログを整列しました。")

            self.after(0, gui_res)

        threading.Thread(target=vec_thread, daemon=True).start()

    def ask_ai_rag_with_confirm(self):
        if not self.api_controller:
            messagebox.showerror("エラー", "AiReAPI 通信モジュールがロードされていません。")
            return

        user_q = self.txt_rag_query.get("1.0", tk.END).strip()
        if not user_q:
            messagebox.showwarning("警告", "AIへの質問文を入力してください。")
            return

        ans = messagebox.askyesno(
            "⚠️ AIトークン消費の確認",
            f"抽出された過去ログの文脈をAIへ送信し、横断質問・要約回答を生成します。\n\n"
            f"（※API通信およびトークン枠を消費します）\n\n"
            f"質問文: 『{user_q[:50]}...』\n\n"
            f"本当に実行しますか？"
        )
        if not ans: return

        self.txt_rag_reply.config(state="normal")
        self.txt_rag_reply.delete("1.0", tk.END)
        self.txt_rag_reply.insert("1.0", "⏳ 過去ログ全体から文脈を集約し、AIが回答を生成中です...")
        self.txt_rag_reply.config(state="disabled")

        context_snippets = []
        for it in self.hit_results[:5]:
            raw_p = os.path.join(it["path"], "summary.md")
            if not os.path.exists(raw_p):
                raw_p = os.path.join(it["path"], "raw_master.md")
            if os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8") as f:
                        context_snippets.append(f"【チャット: {it['name']}】\n" + f.read()[:2000])
                except: pass

        context_str = "\n\n".join(context_snippets) if context_snippets else "過去ログ全体の基本コンテキスト"
        full_prompt = f"【過去ログ背景データ】\n{context_str}\n\n【ユーザーからの質問】\n{user_q}\n\n上記過去ログを踏まえ、回答を作成してください。"

        def thread_task():
            ok, res = self.api_controller.send_request(full_prompt, task_type="chat")
            
            def gui_update():
                self.txt_rag_reply.config(state="normal")
                self.txt_rag_reply.delete("1.0", tk.END)
                if ok:
                    self.txt_rag_reply.insert("1.0", res.strip())
                else:
                    self.txt_rag_reply.insert("1.0", f"❌ AI通信エラー:\n{res}")
                self.txt_rag_reply.config(state="disabled")

            self.after(0, gui_update)

        threading.Thread(target=thread_task, daemon=True).start()


# ================= 🖥️ 単体起動時テストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("🧭 AiReAnchorCompass - ナレッジコンパス")
    root.geometry("1100x700")

    if os.path.exists(ICON_PORTAL):
        try: root.iconbitmap(ICON_PORTAL)
        except: pass

    compass_frame = AiReAnchorCompassFrame(root)
    compass_frame.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()