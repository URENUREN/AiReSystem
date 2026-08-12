# -*- coding: utf-8 -*-
# AiReAnchorForgeTab.pyw - コンテキスト合成 ＆ ChronoTree連動 (マルチスレッド並列爆速スキャン・スマート共通主題名・外部転送連動強化版)
import os
import sys
import json
import re
import datetime
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from collections import Counter

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
    def render_rich_markdown(text_widget, content, base_dir=None, show_rich=True, show_img=True, img_refs=None, filepath=None, on_update_callback=None, progress_bar=None, show_style="simple_md"):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", content if content else "（データがありません）")
        text_widget.config(state="disabled")

try:
    from AiReAPI import AiReAPIController
    HAS_API = True
except ImportError:
    HAS_API = False

try:
    from AiReKnots import AiReKnotsEngine
    HAS_KNOTS = True
except ImportError:
    HAS_KNOTS = False

try:
    from AiReAccessway import AiReAccesswayController
    HAS_ACCESSWAY = True
except ImportError:
    HAS_ACCESSWAY = False

try:
    from AiReChronicleTreeTab import AiReChronicleEngine
    HAS_CHRONICLE = True
except ImportError:
    HAS_CHRONICLE = False

# Windows AppID 登録
try:
    import ctypes
    myappid = 'airelinker.suite.forge.v8'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

# デフォルトプロンプト
DEFAULT_PROMPT_FORGE_FULL = """【指示】以下の複数の対話ログを総合・整理し、全体で話し合われた主要な目的、仕様、結論、成果物を1本の分かりやすいマークダウンにまとめ直してください。"""

DEFAULT_PROMPT_FORGE_TOPIC = """【指示】以下の複数の対話ログの中から、トピック「{topic_word}」に関連するやり取り・発言・仕様部分だけをピンポイントで抽出し、1本に整理統合してください。"""

DEFAULT_PROMPT_FORGE_STORY = """【指示】以下の複数の対話ログから、どのような試行錯誤、エラー、勘違いの足踏みが発生し、どのように解決に至ったかのプロセスを時系列で客観的に抽出しマージしてください。"""

DEFAULT_PROMPT_FORGE_C1_LABEL = "💻 完成コード一括抽出"
DEFAULT_PROMPT_FORGE_C1_PROMPT = """【指示】以下の複数の対話ログから、試行錯誤の過程は一切省き、最終的に完成・決定したソースコードおよび設定仕様のみを綺麗に抽出・統合してください。"""

DEFAULT_PROMPT_FORGE_C2_LABEL = "📝 仕様書・設計書作成"
DEFAULT_PROMPT_FORGE_C2_PROMPT = """【指示】以下の複数の対話ログから、決定したシステム仕様、データ構造、UIデザイン方針を網羅した技術仕様書ドキュメントを作成してください。"""


class UsageHelpForgeDialog(tk.Toplevel):
    """❓ 使い方ヘルプダイアログ"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("❓ AiReAnchorForge 使い方ガイド")
        self.geometry("640x540")
        
        if os.path.exists(ICON_PORTAL):
            try: self.iconbitmap(ICON_PORTAL)
            except: pass

        self.build_widgets()

    def build_widgets(self):
        ttk.Label(self, text="📖 🔨 AiReAnchorForge 概要 ＆ 操作マニュアル", font=("MS Gothic", 10, "bold")).pack(anchor="w", padx=10, pady=8)

        txt_frame = ttk.Frame(self, padding=8)
        txt_frame.pack(fill="both", expand=True)

        txt = tk.Text(txt_frame, wrap="word", font=("MS Gothic", 9), background="#ffffff")
        sb = ttk.Scrollbar(txt_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        guide_text = """======================================================================
 🔨 AiReAnchorForge - コンテキスト合成 ＆ RAG保管庫ワークスペース
======================================================================

【1. 左パネル: ログ選択 ＆ リアルタイム統計】
 ・ツリー上の「📝」マークで要約作成済みチャットが一目で分かります。
 ・「☑ 引き継ぎログのみ表示」をチェックすると、コンパスや他タブから引き継がれたログのみ絞り込めます。

【2. 右パネル: 事前要約 ＆ ChronoTree連携 ＆ 2系統マージ】
 ・「📜 選択チャットを ChronoTree (年表作成) タブへ送る」で年表作成タブへ引き継げます。
 ・「📦 選択チャットを無加工で外部フォルダへ一括エクスポート」はトークン消費0回（無料）で
   外部の任意指定フォルダへ生ログをそのまま安全コピー保存します。
======================================================================
"""
        txt.insert(tk.END, guide_text)
        txt.config(state="disabled")


class AiReAnchorForgeFrame(ttk.Frame):
    """🌟 2系統10分割ボタン ＆ マルチスレッド並列爆速スキャン ＆ 事前要約生成対応コンテキスト合成フレーム"""
    def __init__(self, parent, save_dir=None, main_app=None):
        super().__init__(parent)
        self.main_app = main_app
        
        if main_app:
            self.config = main_app.config
            self.save_dir = main_app.save_dir
        else:
            self.config = self.load_config()
            self.save_dir = save_dir if save_dir else self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))

        self.my_doc_dir = os.path.join(self.save_dir, "my_forge")
        self.my_rag_dir = os.path.join(self.save_dir, "my_RAG_Vault")
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(self.my_doc_dir, exist_ok=True)
        os.makedirs(self.my_rag_dir, exist_ok=True)
        self.output_dir = self.my_doc_dir

        self.api_controller = AiReAPIController(self.config) if HAS_API else None
        self.knots_engine = AiReKnotsEngine(self.config) if HAS_KNOTS else None
        self.accessway_ctrl = AiReAccesswayController(self.config, self.save_dir) if HAS_ACCESSWAY else None
        self.chronicle_engine = AiReChronicleEngine() if HAS_CHRONICLE else None

        self.chat_checks = {}   # {chat_path: True/False}
        self.folder_checks = {} # {folder_name: True/False}

        self.source_priority = ["master", "importer", "scraped", "3rd"]
        self.image_refs = []

        self.build_ui()

        # 他タブからの転送ログが存在すれば自動的にフィルタON
        candidates = self.config.get("forge_candidate_chats", [])
        if candidates:
            self.var_filter_candidates.set(True)

        self.refresh_chat_tree()
        self.update_custom_buttons_from_config()

        # 初回の自動テーマ名設定
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if selected_paths:
            auto_theme = self._auto_generate_theme_name(selected_paths)
            self.entry_out_filename.delete(0, tk.END)
            self.entry_out_filename.insert(0, auto_theme)

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
        self.lbl_path_disp.config(text=f"参照中: [ {new_dir} ]")
        self.refresh_chat_tree()

    def browse_and_set_save_dir(self):
        curr = self.get_active_save_dir()
        selected = filedialog.askdirectory(title="参照するログフォルダを選択", initialdir=curr if os.path.exists(curr) else CURRENT_DIR)
        if selected:
            self.set_active_save_dir(selected)

    def browse_output_dir(self):
        selected = filedialog.askdirectory(title="合成成果物の保存先フォルダを選択", initialdir=self.output_dir)
        if selected:
            self.output_dir = selected
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, self.output_dir)

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

    def update_priority_btn_label(self):
        disp_map = {"master": "🌟マスター", "importer": "📦インポート", "scraped": "📡スクレイプ", "3rd": "🔗3rd"}
        p_str = " ➔ ".join([disp_map.get(k, k) for k in self.source_priority])
        self.btn_priority.config(text=f"🔀 優先順: [ {p_str} ]")

    def _auto_generate_theme_name(self, selected_paths):
        """🌟 転送・選択ログ群全体から共通主要キーワード（主題）を抽出して命名（『他X件』等は完全非表示）"""
        if not selected_paths:
            return ""

        titles = [os.path.basename(p) for p in selected_paths]
        
        words = []
        for t in titles:
            clean_t = re.sub(r'^(AiReSystem|AiReAnchor|AiReLinker|AI|Google AI Studio)_?', '', t)
            clean_t = re.sub(r'(\.md|\.txt)$', '', clean_t)
            tokens = re.split(r'[\s_\-\:\/\.\(\)]+', clean_t)
            for tok in tokens:
                if len(tok) >= 2 and not tok.isdigit():
                    words.append(tok)

        if not words:
            return f"Forge_{os.path.basename(selected_paths[0])[:15]}"

        counts = Counter(words)
        top_words = [w for w, _ in counts.most_common(2)]
        
        main_topic = "_".join(top_words) if top_words else words[0]
        return f"Forge_{main_topic}"

    def build_ui(self):
        top_bar = ttk.Frame(self, padding=(4, 2))
        top_bar.pack(fill="x", side="top")

        ttk.Button(top_bar, text="📂 参照...", command=self.browse_and_set_save_dir).pack(side="left", padx=2)
        self.lbl_path_disp = ttk.Label(top_bar, text=f"現在参照中: [ {self.get_active_save_dir()} ]", font=("MS Gothic", 8, "bold"), foreground="#0284c7")
        self.lbl_path_disp.pack(side="left", padx=6)

        self.btn_priority = ttk.Button(top_bar, text="🔀 優先順: [ 🌟マスター ➔ 📦インポート ➔ 📡スクレイプ ➔ 🔗3rd ]", command=self.cycle_source_priority)
        self.btn_priority.pack(side="left", padx=6)

        ttk.Button(top_bar, text="🔄 設定再ロード", command=self.update_custom_buttons_from_config).pack(side="right", padx=2)
        ttk.Button(top_bar, text="❓ 使い方ヘルプ", command=lambda: UsageHelpForgeDialog(self)).pack(side="right", padx=4)

        self.forge_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.forge_pane.pack(fill="both", expand=True, padx=4, pady=4)

        # =========================================================================
        # 左パネル: ログ選択 ＆ フィルタツリー ＆ 統計インジケーター
        # =========================================================================
        left_p = ttk.Frame(self.forge_pane, width=320)
        self.forge_pane.add(left_p, weight=1)

        tree_lf = ttk.LabelFrame(left_p, text=" 🎛 合成対象ログ選択 ", padding=6)
        tree_lf.pack(fill="both", expand=True, pady=2)

        filter_f = ttk.Frame(tree_lf)
        filter_f.pack(fill="x", pady=(0, 4))

        self.var_filter_candidates = tk.BooleanVar(value=False)
        self.chk_candidate = ttk.Checkbutton(
            filter_f, 
            text="☑ 引き継ぎログのみ表示", 
            variable=self.var_filter_candidates, 
            command=self.refresh_chat_tree
        )
        self.chk_candidate.pack(side="left")

        act_bar = ttk.Frame(tree_lf)
        act_bar.pack(fill="x", pady=2)
        ttk.Button(act_bar, text="☑ 全選択", command=self.select_all_chats).pack(side="left", padx=2)
        ttk.Button(act_bar, text="☐ 全解除", command=self.deselect_all_chats).pack(side="left", padx=2)
        ttk.Button(act_bar, text="🧹 全除外", command=self.clear_candidates_and_list).pack(side="left", padx=2)
        ttk.Button(act_bar, text="➕ 追加", command=self.add_chat_manually).pack(side="left", padx=2)
        ttk.Button(act_bar, text="🗑 除外", command=self.remove_selected_chat).pack(side="left", padx=2)

        tree_container = ttk.Frame(tree_lf)
        tree_container.pack(fill="both", expand=True, pady=2)

        self.tree_chats = ttk.Treeview(tree_container, show="tree", selectmode="browse")
        sb_tree = ttk.Scrollbar(tree_container, command=self.tree_chats.yview)
        self.tree_chats.configure(yscrollcommand=sb_tree.set)

        self.tree_chats.pack(side="left", fill="both", expand=True)
        sb_tree.pack(side="right", fill="y")
        self.tree_chats.bind("<Button-1>", self.on_tree_click)

        # 統計情報インジケーター
        stats_lf = ttk.LabelFrame(left_p, text=" 📊 選択ログ統計インジケーター ", padding=6)
        stats_lf.pack(fill="x", side="bottom", pady=4)

        self.lbl_stats_count = ttk.Label(stats_lf, text="・ 選択数: 0 件 (うち要約未生成: 0 件)", font=("MS Gothic", 8))
        self.lbl_stats_count.pack(anchor="w", pady=1)

        self.lbl_stats_chars = ttk.Label(stats_lf, text="・ 生ログ合計: 0 文字 (未生成分: 0 文字)", font=("MS Gothic", 8, "bold"), foreground="#0284c7")
        self.lbl_stats_chars.pack(anchor="w", pady=1)

        self.lbl_stats_api = ttk.Label(stats_lf, text="・ 想定API送信回数: 全件約 0 回 / 未生成のみ約 0 回", font=("MS Gothic", 8), foreground="#d97706")
        self.lbl_stats_api.pack(anchor="w", pady=1)

        # =========================================================================
        # 中央パネル: 合成成果物プレビュー ＆ 出力先設定
        # =========================================================================
        center_p = ttk.Frame(self.forge_pane, width=460)
        self.forge_pane.add(center_p, weight=3)

        out_lf = ttk.LabelFrame(center_p, text=" 📌 出力設定 ＆ 成果物プレビュー ", padding=6)
        out_lf.pack(fill="both", expand=True, pady=2)

        out_cfg_f = ttk.Frame(out_lf)
        out_cfg_f.pack(fill="x", pady=2)

        row_d = ttk.Frame(out_cfg_f)
        row_d.pack(fill="x", pady=1)
        ttk.Label(row_d, text="保存フォルダ:", font=("MS Gothic", 8, "bold")).pack(side="left", padx=2)
        self.entry_out_dir = ttk.Entry(row_d, font=("MS Gothic", 8))
        self.entry_out_dir.pack(side="left", fill=tk.X, expand=True, padx=2)
        self.entry_out_dir.insert(0, self.output_dir)
        ttk.Button(row_d, text="📂 変更...", width=7, command=self.browse_output_dir).pack(side="right", padx=2)

        row_f = ttk.Frame(out_cfg_f)
        row_f.pack(fill="x", pady=1)
        ttk.Label(row_f, text="出力テーマ名:", font=("MS Gothic", 8, "bold")).pack(side="left", padx=2)
        self.entry_out_filename = ttk.Entry(row_f, font=("MS Gothic", 9))
        self.entry_out_filename.pack(side="left", fill=tk.X, expand=True, padx=2)
        ttk.Label(row_f, text="(※空欄で自動命名)", font=("MS Gothic", 8), foreground="#64748b").pack(side="right", padx=2)

        prev_txt_f = ttk.Frame(out_lf)
        prev_txt_f.pack(fill="both", expand=True, pady=4)

        self.forge_preview_text = tk.Text(prev_txt_f, background="#ffffff", wrap="word")
        self.forge_preview_text.pack(side="left", fill="both", expand=True)

        sb_prev = ttk.Scrollbar(prev_txt_f, command=self.forge_preview_text.yview)
        sb_prev.pack(side="right", fill="y")
        self.forge_preview_text.configure(yscrollcommand=sb_prev.set)

        self.forge_preview_text.insert(tk.END, "💡 左パネルで合成対象のチャットにチェックを入れた後、右パネルのボタンからAI合成命令を実行してください。")
        self.forge_preview_text.config(state="disabled")

        # =========================================================================
        # 右パネル: AI合成 ＆ ChronoTree/外部エクスポート
        # =========================================================================
        right_p = ttk.Frame(self.forge_pane, width=380)
        self.forge_pane.add(right_p, weight=2)

        self.right_v_pane = tk.PanedWindow(right_p, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
        self.right_v_pane.pack(fill="both", expand=True, pady=2)

        top_ai_f = ttk.Frame(self.right_v_pane)
        self.right_v_pane.add(top_ai_f, minsize=350, height=520)

        ai_forge_f = ttk.LabelFrame(top_ai_f, text=" 🤖 AI合成 ＆ 外部・年表連携オーケストレーター ", padding=6)
        ai_forge_f.pack(fill="both", expand=True)

        # 🌟 独立枠 1: 要約事前準備
        pre_sum_lf = ttk.LabelFrame(ai_forge_f, text=" 🛠 ステップ1: 各チャットの要約事前準備 (マージなし) ", padding=6)
        pre_sum_lf.pack(fill="x", pady=2)

        btn_pre_sum = ttk.Button(
            pre_sum_lf, 
            text="⚡ 選択チャットの未作成要約を一括生成・保存 (ポータル同等処理)", 
            command=self.run_pre_generate_summaries
        )
        btn_pre_sum.pack(fill="x", pady=2)

        # 🌟 独立枠 2: ChronoTree(年表)連携 ＆ 無加工外部エクスポート
        rag_vault_lf = ttk.LabelFrame(ai_forge_f, text=" 📦 ステップ2: 外部保存 (無加工) ＆ ChronoTree (年表) 連携 ", padding=6)
        rag_vault_lf.pack(fill="x", pady=2)

        btn_export_external = ttk.Button(
            rag_vault_lf,
            text="📦 選択チャットを無加工で外部フォルダへ一括エクスポート",
            command=self.export_unprocessed_to_external_folder
        )
        btn_export_external.pack(fill="x", pady=2)

        btn_send_chronicle = ttk.Button(
            rag_vault_lf,
            text="📜 選択チャットを ChronoTree (年表作成) タブへ送る",
            command=self.send_selected_to_chronicle
        )
        btn_send_chronicle.pack(fill="x", pady=2)

        # 🌟 独立枠 3: 2系統プリセット一括合成マージ命令
        preset_lf = ttk.LabelFrame(ai_forge_f, text=" 🔨 ステップ3: 2系統 プリセット一括合成マージ命令 ", padding=6)
        preset_lf.pack(fill="x", pady=2)

        p_grid = ttk.Frame(preset_lf)
        p_grid.pack(fill="x", pady=1)
        p_grid.columnconfigure(0, weight=1)
        p_grid.columnconfigure(1, weight=1)

        ttk.Label(p_grid, text="📄 生データ(Raw)から直接マージ", font=("MS Gothic", 8, "bold"), foreground="#0284c7").grid(row=0, column=0, sticky="w", padx=2, pady=1)
        ttk.Label(p_grid, text="📝 要約(Summary)から集約マージ", font=("MS Gothic", 8, "bold"), foreground="#16a34a").grid(row=0, column=1, sticky="w", padx=2, pady=1)

        ttk.Button(p_grid, text="📄 全文マージ＆概要", command=lambda: self.run_ai_forge_task("full_merge", "raw")).grid(row=1, column=0, sticky="ew", padx=1, pady=2)
        ttk.Button(p_grid, text="📝 全文マージ＆概要", command=lambda: self.run_ai_forge_task("full_merge", "summary")).grid(row=1, column=1, sticky="ew", padx=1, pady=2)

        ttk.Button(p_grid, text="📄 特定トピック抽出", command=lambda: self.run_ai_forge_task("topic_extract", "raw")).grid(row=2, column=0, sticky="ew", padx=1, pady=2)
        ttk.Button(p_grid, text="📝 特定トピック抽出", command=lambda: self.run_ai_forge_task("topic_extract", "summary")).grid(row=2, column=1, sticky="ew", padx=1, pady=2)

        ttk.Button(p_grid, text="📄 試行錯誤ストーリー", command=lambda: self.run_ai_forge_task("story_merge", "raw")).grid(row=3, column=0, sticky="ew", padx=1, pady=2)
        ttk.Button(p_grid, text="📝 試行錯誤ストーリー", command=lambda: self.run_ai_forge_task("story_merge", "summary")).grid(row=3, column=1, sticky="ew", padx=1, pady=2)

        self.btn_c1_raw = ttk.Button(p_grid, text="📄 カスタム1", command=lambda: self.run_ai_forge_task("custom_1", "raw"))
        self.btn_c1_raw.grid(row=4, column=0, sticky="ew", padx=1, pady=2)

        self.btn_c1_sum = ttk.Button(p_grid, text="📝 カスタム1", command=lambda: self.run_ai_forge_task("custom_1", "summary"))
        self.btn_c1_sum.grid(row=4, column=1, sticky="ew", padx=1, pady=2)

        self.btn_c2_raw = ttk.Button(p_grid, text="📄 カスタム2", command=lambda: self.run_ai_forge_task("custom_2", "raw"))
        self.btn_c2_raw.grid(row=5, column=0, sticky="ew", padx=1, pady=2)

        self.btn_c2_sum = ttk.Button(p_grid, text="📝 カスタム2", command=lambda: self.run_ai_forge_task("custom_2", "summary"))
        self.btn_c2_sum.grid(row=5, column=1, sticky="ew", padx=1, pady=2)

        # 手動カスタム指示プロンプト
        custom_lf = ttk.LabelFrame(ai_forge_f, text=" 📝 カスタム指示プロンプト ", padding=6)
        custom_lf.pack(fill="both", expand=True, pady=2)

        ttk.Label(custom_lf, text="AIへの手動合成・編集指示を入力:", font=("MS Gothic", 8), foreground="#475569").pack(anchor="w")

        self.txt_custom_prompt = tk.Text(custom_lf, height=2, font=("MS Gothic", 9), wrap="word")
        self.txt_custom_prompt.pack(fill="both", expand=True, pady=2)

        c_btn_f = ttk.Frame(custom_lf)
        c_btn_f.pack(fill="x", pady=1)

        ttk.Button(c_btn_f, text="📄 生データで手動合成", command=lambda: self.run_ai_forge_task("custom", "raw")).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(c_btn_f, text="📝 要約で手動合成", command=lambda: self.run_ai_forge_task("custom", "summary")).pack(side="right", expand=True, fill="x", padx=1)

        # 下部: 緑のプログレスバー ＆ ログコンソール
        bot_log_f = ttk.Frame(self.right_v_pane)
        self.right_v_pane.add(bot_log_f, minsize=110, height=140)

        log_lf = ttk.LabelFrame(bot_log_f, text=" 📜 実行ステータス ＆ 進捗インジケーター ", padding=6)
        log_lf.pack(fill="both", expand=True)

        self.prog_container = ttk.Frame(log_lf)
        self.prog_container.pack(fill="x", pady=(0, 4))

        self.lbl_prog_status = ttk.Label(self.prog_container, text="⏳ 待機中...", font=("MS Gothic", 8, "bold"), foreground="#0284c7")
        self.lbl_prog_status.pack(anchor="w", pady=1)

        self.prog_bar = ttk.Progressbar(self.prog_container, mode="determinate")
        self.prog_bar.pack(fill="x", expand=True)

        self.txt_log = tk.Text(log_lf, background="#f8fafc", font=("MS Gothic", 8), wrap="word")
        sb_log = ttk.Scrollbar(log_lf, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb_log.set)
        
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb_log.pack(side="right", fill="y")

    def _worker_scan_chat_stats(self, cp, max_chunk_chars):
        """🌟 マルチスレッド用 1チャットの文字数・要約有無・想定API回数一斉計算ワーカー"""
        try:
            has_sum = (self.find_summary_file_path(cp) is not None)
            
            raw_p = os.path.join(cp, "raw_master.md")
            if not os.path.exists(raw_p):
                for sk in ["importer", "scraped", "3rd"]:
                    sp = os.path.join(cp, sk)
                    if os.path.exists(sp):
                        for f in os.listdir(sp):
                            if f.endswith(".md"): raw_p = os.path.join(sp, f); break
                        if os.path.exists(raw_p): break

            c_len = 0
            parts = 1
            if os.path.exists(raw_p):
                try:
                    c_len = os.path.getsize(raw_p)
                    parts = (c_len // max_chunk_chars) + 2
                except: pass

            return cp, has_sum, c_len, parts
        except:
            return cp, False, 0, 1

    def find_summary_file_path(self, chat_folder):
        if not chat_folder or not os.path.exists(chat_folder): return None
        chat_name = os.path.basename(chat_folder)
        candidates = [
            os.path.join(chat_folder, f"summary_{chat_name}.md"),
            os.path.join(chat_folder, "summary.md"),
            os.path.join(chat_folder, "summary_master.md")
        ]
        for cand in candidates:
            if os.path.exists(cand): return cand
        for f in os.listdir(chat_folder):
            if f.startswith("summary_") and f.endswith(".md"):
                return os.path.join(chat_folder, f)
        return None

    def update_custom_buttons_from_config(self):
        cfg = self.load_config()
        c1_lbl = cfg.get("prompt_forge_c1_label", DEFAULT_PROMPT_FORGE_C1_LABEL)
        c2_lbl = cfg.get("prompt_forge_c2_label", DEFAULT_PROMPT_FORGE_C2_LABEL)

        if c1_lbl:
            self.btn_c1_raw.config(text=f"📄 {c1_lbl}", state="normal")
            self.btn_c1_sum.config(text=f"📝 {c1_lbl}", state="normal")
        else:
            self.btn_c1_raw.config(text="📄 カスタム1", state="disabled")
            self.btn_c1_sum.config(text="📝 カスタム1", state="disabled")

        if c2_lbl:
            self.btn_c2_raw.config(text=f"📄 {c2_lbl}", state="normal")
            self.btn_c2_sum.config(text=f"📝 {c2_lbl}", state="normal")
        else:
            self.btn_c2_raw.config(text="📄 カスタム2", state="disabled")
            self.btn_c2_sum.config(text="📝 カスタム2", state="disabled")

    def log(self, msg):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"[{now}] {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def clear_candidates_and_list(self):
        """🌟 候補・選択リストの完全リセットクリア（全除外）"""
        self.config["forge_candidate_chats"] = []
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except: pass

        self.chat_checks.clear()
        self.folder_checks.clear()
        self.var_filter_candidates.set(False)
        self.refresh_chat_tree()
        self.entry_out_filename.delete(0, tk.END)
        messagebox.showinfo("初期化", "合成対象の選択リストおよび候補リストを完全消去・リセットしました。")

    def add_chat_manually(self):
        active_dir = self.get_active_save_dir()
        selected = filedialog.askdirectory(title="追加するチャットフォルダを選択", initialdir=active_dir)
        if selected and os.path.isdir(selected):
            self.chat_checks[selected] = True
            candidates = self.config.get("forge_candidate_chats", [])
            if selected not in candidates:
                candidates.append(selected)
                self.config["forge_candidate_chats"] = candidates
                try:
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                        json.dump(self.config, f, indent=4, ensure_ascii=False)
                except: pass
            self.refresh_chat_tree()

    def remove_selected_chat(self):
        item = self.tree_chats.selection()
        if not item: return
        vals = self.tree_chats.item(item[0], "values")
        if vals and vals[0] == "chat":
            c_path = vals[1]
            self.chat_checks[c_path] = False
            candidates = self.config.get("forge_candidate_chats", [])
            if c_path in candidates:
                candidates.remove(c_path)
                self.config["forge_candidate_chats"] = candidates
                try:
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                        json.dump(self.config, f, indent=4, ensure_ascii=False)
                except: pass
            self.refresh_chat_tree()

    def refresh_chat_tree(self):
        """🌟 マルチスレッド並列処理（ThreadPoolExecutor）によるツリー構築＆統計計算の爆速化"""
        self.tree_chats.delete(*self.tree_chats.get_children())
        active_dir = self.get_active_save_dir()
        self.lbl_path_disp.config(text=f"現在参照中: [ {active_dir} ]")

        if not os.path.exists(active_dir): return

        candidates = self.config.get("forge_candidate_chats", [])
        is_filter_candidates = self.var_filter_candidates.get()

        folder_priority = ["Google AI Studio", "Gemini", "ChatGPT", "Claude", "AiReChat"]
        all_folders = [f for f in os.listdir(active_dir) if os.path.isdir(os.path.join(active_dir, f)) and f not in ["my_documents", "my_forge", "my_RAG_Vault"]]

        def sort_key(name):
            if name in folder_priority: return (0, folder_priority.index(name))
            return (1, name)

        sorted_ai_folders = sorted(all_folders, key=sort_key)
        chat_entries = []

        for ai_folder in sorted_ai_folders:
            ai_path = os.path.join(active_dir, ai_folder)
            chats = sorted(os.listdir(ai_path)) if os.path.exists(ai_path) else []

            for chat in chats:
                chat_path = os.path.join(ai_path, chat)
                if not os.path.isdir(chat_path): continue
                if is_filter_candidates and candidates and chat_path not in candidates:
                    continue
                chat_entries.append((ai_folder, chat, chat_path))

        # 🌟 全チャットの要約有無・文字数をマルチスレッドで一斉並列スキャン
        chat_info_cache = {}
        chat_paths_to_scan = [cp for _, _, cp in chat_entries]
        max_chunk_chars = self.config.get("max_summary_text_length", 50000)

        if chat_paths_to_scan:
            max_workers = min(32, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._worker_scan_chat_stats, cp, max_chunk_chars) for cp in chat_paths_to_scan]
                for future in as_completed(futures):
                    cp, has_sum, c_len, parts = future.result()
                    chat_info_cache[cp] = (has_sum, c_len, parts)

        grouped_chats = {}
        for ai_folder, chat, chat_path in chat_entries:
            grouped_chats.setdefault(ai_folder, []).append((chat, chat_path))

        for ai_folder in sorted_ai_folders:
            if ai_folder not in grouped_chats: continue
            items = grouped_chats[ai_folder]

            f_mark = "☑" if self.folder_checks.get(ai_folder, True) else "☐"
            p_node = self.tree_chats.insert("", "end", text=f"{f_mark} 📁 {ai_folder}", open=True, values=("folder", ai_folder))

            for chat, chat_path in items:
                default_chk = True if (candidates and chat_path in candidates) else self.chat_checks.get(chat_path, False)
                self.chat_checks[chat_path] = default_chk

                c_mark = "☑" if default_chk else "☐"
                has_sum, _, _ = chat_info_cache.get(chat_path, (False, 0, 1))
                sum_mark = "📝 " if has_sum else "　 "

                self.tree_chats.insert(p_node, "end", text=f"{c_mark} {sum_mark}💬 {chat}", values=("chat", chat_path))

        self.update_statistics_indicator()

    def on_tree_click(self, event):
        """🌟 [+] / [-] 開閉アイコン（indicator）押し時はチェックトグルを完全遮断！"""
        element = self.tree_chats.identify_element(event.x, event.y)
        if element in ["indicator", "space"]:
            return

        item = self.tree_chats.identify_row(event.y)
        if not item: return

        vals = self.tree_chats.item(item, "values")
        if not vals: return

        item_type = vals[0]
        item_id = vals[1]

        # チェックマーク領域 (X座標 20px 〜 60px) のみトグル実行
        if 20 <= event.x <= 60:
            if item_type == "folder":
                curr = self.folder_checks.get(item_id, True)
                self.folder_checks[item_id] = not curr
                active_dir = self.get_active_save_dir()
                ai_p = os.path.join(active_dir, item_id)
                if os.path.exists(ai_p):
                    for c in os.listdir(ai_p):
                        cp = os.path.join(ai_p, c)
                        if os.path.isdir(cp): self.chat_checks[cp] = not curr
                self.redraw_tree_checks()
            elif item_type == "chat":
                curr = self.chat_checks.get(item_id, False)
                self.chat_checks[item_id] = not curr
                self.redraw_tree_checks()

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
                        
                        has_sum = self.find_summary_file_path(c_path) is not None
                        sum_mark = "📝 " if has_sum else "　 "

                        c_name = os.path.basename(c_path)
                        self.tree_chats.item(c_item, text=f"{c_mark} {sum_mark}💬 {c_name}")

        self.update_statistics_indicator()

    def update_statistics_indicator(self):
        """🌟 マルチスレッド並列処理による高速統計計算"""
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        total_count = len(selected_paths)
        if not selected_paths:
            self.lbl_stats_count.config(text="・ 選択数: 0 件 (うち要約未生成: 0 件)")
            self.lbl_stats_chars.config(text="・ 生ログ合計: 0 文字 (未生成分: 0 文字)")
            self.lbl_stats_api.config(text="・ 想定API送信回数: 全件約 0 回 / 未生成のみ約 0 回")
            return

        max_chunk_chars = self.config.get("max_summary_text_length", 50000)

        unsummarized_count = 0
        total_chars_all = 0
        total_parts_all = 0
        unsum_chars = 0
        unsum_parts = 0

        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._worker_scan_chat_stats, cp, max_chunk_chars) for cp in selected_paths]
            for future in as_completed(futures):
                cp, has_sum, c_len, parts = future.result()
                total_chars_all += c_len
                total_parts_all += parts

                if not has_sum:
                    unsummarized_count += 1
                    unsum_chars += c_len
                    unsum_parts += parts

        self.lbl_stats_count.config(text=f"・ 選択数: {total_count} 件 (うち要約未生成: {unsummarized_count} 件)")
        self.lbl_stats_chars.config(text=f"・ 生ログ合計: {total_chars_all:,} 文字 (未生成分: {unsum_chars:,} 文字)")
        self.lbl_stats_api.config(text=f"・ 想定API送信回数: 全件約 {total_parts_all} 回 / 未生成のみ約 {unsum_parts} 回")

    def select_all_chats(self):
        for k in self.folder_checks: self.folder_checks[k] = True
        for k in self.chat_checks: self.chat_checks[k] = True
        self.redraw_tree_checks()

    def deselect_all_chats(self):
        for k in self.folder_checks: self.folder_checks[k] = False
        for k in self.chat_checks: self.chat_checks[k] = False
        self.redraw_tree_checks()

    def run_pre_generate_summaries(self):
        if not self.accessway_ctrl:
            messagebox.showerror("エラー", "AiReAccessway コントローラーが未ロードです。")
            return

        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            messagebox.showwarning("警告", "対象のチャットにチェックを入れて選択してください。")
            return

        unsummarized_chats = [cp for cp in selected_paths if not self.find_summary_file_path(cp)]

        if not unsummarized_chats:
            messagebox.showinfo("案内", "選択されたすべてのチャットには、すでに要約ファイル(summary_*.md)が作成されています！")
            return

        ans = messagebox.askyesno(
            "事前要約生成の確認", 
            f"未要約のチャット 【 {len(unsummarized_chats)} 件 】 に対し、個別要約・ストーリーを一括生成しますか？\n\n"
            f"（※ポータルタブと全く同じ高品質エンジンで各チャット内に保存します。マージは行いません）"
        )
        if not ans: return

        total_tasks = len(unsummarized_chats)
        self.prog_bar.config(maximum=total_tasks, value=0)
        self.lbl_prog_status.config(text=f"⏳ 一括要約処理中... [ 0 / {total_tasks} 件完了 ] (0%)", foreground="#0284c7")
        self.log(f"⏳ 事前要約一括処理を開始: 全 {total_tasks} 件...")

        def thread_task():
            success_cnt = 0
            for idx, cp in enumerate(unsummarized_chats):
                c_name = os.path.basename(cp)
                raw_p = os.path.join(cp, "raw_master.md")
                if not os.path.exists(raw_p):
                    for sk in ["importer", "scraped", "3rd"]:
                        sp = os.path.join(cp, sk)
                        if os.path.exists(sp):
                            for f in os.listdir(sp):
                                if f.endswith(".md"): raw_p = os.path.join(sp, f); break

                if not os.path.exists(raw_p) and self.knots_engine:
                    res, _ = self.knots_engine.build_integrated_master(cp)
                    if res:
                        tmp_p = os.path.join(cp, "_temp_raw.md")
                        with open(tmp_p, "w", encoding="utf-8") as f: f.write(res["master_markdown"])
                        raw_p = tmp_p

                if os.path.exists(raw_p):
                    def cb(msg): self.log(f"[{idx+1}/{total_tasks}] 『{c_name}』: {msg}")
                    ok, _ = self.accessway_ctrl.process_chat_summary_task(cp, raw_p, log_callback=cb)
                    if ok: success_cnt += 1

                tmp_p = os.path.join(cp, "_temp_raw.md")
                if os.path.exists(tmp_p): os.remove(tmp_p)

                completed = idx + 1
                pct = int((completed / total_tasks) * 100)
                def update_prog(c=completed, p=pct):
                    self.prog_bar.config(value=c)
                    self.lbl_prog_status.config(text=f"⏳ 一括要約処理中... [ {c} / {total_tasks} 件完了 ] ({p}%)")
                self.after(0, update_prog)

            def gui_done():
                self.lbl_prog_status.config(text=f"🎉 事前要約完了！ [ {success_cnt} / {total_tasks} 件完了 ] (100%)", foreground="#16a34a")
                self.log(f"🎉 事前要約一括完了: {success_cnt}/{total_tasks} 件の要約を生成しました！")
                messagebox.showinfo("完了", f"{success_cnt} 件のチャットに要約ストーリー(summary_*.md)を一括生成・保存しました！")
                self.redraw_tree_checks()
                if self.main_app and hasattr(self.main_app, "refresh_portal_data"):
                    self.main_app.refresh_portal_data()

            self.after(0, gui_done)

        threading.Thread(target=thread_task, daemon=True).start()

    def _worker_copy_export(self, cp, target_export_folder):
        """🌟 マルチスレッド用 無加工外部並列コピーワーカー"""
        try:
            chat_name = os.path.basename(cp)
            target_md = None
            
            p_file = os.path.join(cp, "raw_master.md")
            if os.path.exists(p_file):
                target_md = p_file
            else:
                for p_key in self.source_priority:
                    sp = os.path.join(cp, p_key)
                    if os.path.exists(sp):
                        for f in os.listdir(sp):
                            if f.endswith(".md"): target_md = os.path.join(sp, f); break
                    if target_md: break

            if target_md and os.path.exists(target_md):
                dst_file = os.path.join(target_export_folder, f"{chat_name}.md")
                shutil.copy2(target_md, dst_file)
                return True
        except: pass
        return False

    def export_unprocessed_to_external_folder(self):
        """🌟 選択チャットの生ログを無加工で外部指定フォルダへ一括並列エクスポート"""
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            messagebox.showwarning("警告", "対象のチャットにチェックを入れて選択してください。")
            return

        target_root_dir = filedialog.askdirectory(title="エクスポート先の外部フォルダを選択してください")
        if not target_root_dir: return

        theme_name = self.entry_out_filename.get().strip()
        if not theme_name or theme_name.startswith("Forge_"):
            theme_name = self._auto_generate_theme_name(selected_paths)

        theme_name = re.sub(r'[\\/*?:"<>|]', "_", theme_name).strip()
        
        export_folder_name = f"Forge_Raw_{theme_name}"
        target_export_folder = os.path.join(target_root_dir, export_folder_name)
        os.makedirs(target_export_folder, exist_ok=True)

        self.log(f"📦 外部無加工並列エクスポートを開始: 『{target_export_folder}』 (全 {len(selected_paths)} 件)...")

        copied_count = 0
        max_workers = min(32, (os.cpu_count() or 4) * 2)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._worker_copy_export, cp, target_export_folder) for cp in selected_paths]
            for future in as_completed(futures):
                if future.result():
                    copied_count += 1

        self.log(f"🎉 外部無加工エクスポート完了: 【{copied_count} 件】 の元ログをそのまま保存しました！")
        messagebox.showinfo(
            "外部エクスポート完了", 
            f"選択された 【{copied_count} 件】 のチャットログを無加工のまま外部へ書き出しました！\n\n"
            f"・保存場所: {target_export_folder}/\n\n"
            f"（※API通信・トークン消費0回）"
        )

    def send_selected_to_chronicle(self):
        """🌟 選択中のチャットを ChronoTree (年表作成) タブ (Index 3) へ一括転送"""
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths:
            messagebox.showwarning("警告", "対象のチャットにチェックを入れて選択してください。")
            return

        self.config["forge_candidate_chats"] = selected_paths
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except: pass

        if self.main_app and hasattr(self.main_app, "switch_to_chronicle_with_candidates"):
            self.main_app.switch_to_chronicle_with_candidates(selected_paths)
            messagebox.showinfo("ChronoTree連携", f"【{len(selected_paths)} 件】のチャットを ChronoTree タブへ送信し、自動切り替えました！")
        else:
            messagebox.showinfo("送信完了", f"【{len(selected_paths)} 件】のチャットパスを選択保持しました。")

    def collect_selected_chat_contents(self, source_mode="raw"):
        selected_paths = [cp for cp, chk in self.chat_checks.items() if chk and os.path.exists(cp)]
        if not selected_paths: return [], ""

        def get_chat_start_time(cp):
            raw_p = os.path.join(cp, "raw_master.md")
            if not os.path.exists(raw_p):
                for sk in ["importer", "scraped", "3rd"]:
                    sp = os.path.join(cp, sk)
                    if os.path.exists(sp):
                        for f in os.listdir(sp):
                            if f.endswith(".md"): raw_p = os.path.join(sp, f); break
            if raw_p and os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8") as f: c = f.read(2000)
                    m = re.search(r'true_start_time:\s*"([^"]+)"', c)
                    if m: return m.group(1)
                except: pass
            return "9999-99-99 99:99:99"

        sorted_paths = sorted(selected_paths, key=get_chat_start_time)

        collected_texts = []
        titles = []

        for chat_folder in sorted_paths:
            chat_name = os.path.basename(chat_folder)
            titles.append(chat_name)

            target_md = None
            if source_mode == "summary":
                target_md = self.find_summary_file_path(chat_folder)

            if not target_md:
                for p_key in self.source_priority:
                    if p_key == "master":
                        p_file = os.path.join(chat_folder, "raw_master.md")
                        if os.path.exists(p_file): target_md = p_file; break
                    else:
                        sp = os.path.join(chat_folder, p_key)
                        if os.path.exists(sp):
                            for f in os.listdir(sp):
                                if f.endswith(".md"): target_md = os.path.join(sp, f); break
                        if target_md: break

            if not target_md or not os.path.exists(target_md):
                target_md = os.path.join(chat_folder, "summary.md")

            if target_md and os.path.exists(target_md):
                try:
                    with open(target_md, "r", encoding="utf-8") as f:
                        body = f.read()
                    if body.startswith("---"):
                        parts = body.split("---")
                        if len(parts) >= 3: body = "---".join(parts[2:]).strip()

                    collected_texts.append(f"【チャットログ: {chat_name}】\n{body}")
                except: pass

        return titles, "\n\n" + ("="*60) + "\n\n".join(collected_texts)

    def run_ai_forge_task(self, task_type, source_mode="raw"):
        if not self.api_controller:
            messagebox.showerror("エラー", "AiReAPI 通信モジュールがロードされていません。")
            return

        titles, combined_text = self.collect_selected_chat_contents(source_mode=source_mode)
        if not combined_text:
            messagebox.showwarning("警告", "合成対象のチャットにチェックを入れて選択してください。")
            return

        cfg = self.load_config()
        custom_p = self.txt_custom_prompt.get("1.0", tk.END).strip()
        
        prompt_instruction = ""
        task_label = ""
        src_label = "生データ(Raw)" if source_mode == "raw" else "要約(Summary)"

        if task_type == "full_merge":
            task_label = f"全文マージ ＆ 概要 [{src_label}]"
            prompt_instruction = cfg.get("prompt_forge_full", DEFAULT_PROMPT_FORGE_FULL)

        elif task_type == "topic_extract":
            task_label = f"特定トピック部分抽出 [{src_label}]"
            base_prompt = cfg.get("prompt_forge_topic", DEFAULT_PROMPT_FORGE_TOPIC)
            
            topic_word = custom_p
            if not topic_word:
                topic_word = simpledialog.askstring(
                    "抽出トピック指定", 
                    "抽出・合成したい特定のキーワードやトピックを入力してください:\n(例: SLI, Tkinter, バグ修正, 仕様決定)",
                    parent=self
                )
                if not topic_word: return
                self.txt_custom_prompt.delete("1.0", tk.END)
                self.txt_custom_prompt.insert(tk.END, topic_word)

            prompt_instruction = base_prompt.format(topic_word=topic_word) if "{topic_word}" in base_prompt else f"{base_prompt}\n対象トピック: {topic_word}"

        elif task_type == "story_merge":
            task_label = f"試行錯誤ストーリー [{src_label}]"
            prompt_instruction = cfg.get("prompt_forge_story", DEFAULT_PROMPT_FORGE_STORY)

        elif task_type == "custom_1":
            c1_lbl = cfg.get("prompt_forge_c1_label", DEFAULT_PROMPT_FORGE_C1_LABEL)
            task_label = f"{c1_lbl} [{src_label}]"
            prompt_instruction = cfg.get("prompt_forge_c1_prompt", DEFAULT_PROMPT_FORGE_C1_PROMPT)

        elif task_type == "custom_2":
            c2_lbl = cfg.get("prompt_forge_c2_label", DEFAULT_PROMPT_FORGE_C2_LABEL)
            task_label = f"{c2_lbl} [{src_label}]"
            prompt_instruction = cfg.get("prompt_forge_c2_prompt", DEFAULT_PROMPT_FORGE_C2_PROMPT)

        else:
            task_label = f"手動カスタムAI合成 [{src_label}]"
            prompt_instruction = custom_p if custom_p else "【指示】以下の複数の対話ログを元に、内容を整理統合してください。"

        ans = messagebox.askyesno(
            "⚠️ AIトークン消費の確認",
            f"選択された 【{len(titles)} 件】 のチャットログを時系列順に整列し、『{task_label}』を実行します。\n\n"
            f"（※API通信およびトークン枠を消費します）\n\n"
            f"本当に実行しますか？"
        )
        if not ans: return

        self.log(f"⏳ 処理開始: 『{task_label}』 (対象ログ: {len(titles)} 件)...")

        full_prompt = f"{prompt_instruction}\n\n【時系列合体対象対話ログデータ】\n{combined_text}"

        def thread_task():
            ok, res = self.api_controller.send_request(full_prompt, task_type="summary", log_callback=self.log)
            
            def gui_update():
                if ok:
                    merged_result_md = res.strip()
                    self.log(f"✅ AI合成完了！成果物を保存・描画します。")

                    out_fname = self.entry_out_filename.get().strip()
                    if not out_fname:
                        out_fname = self._auto_generate_theme_name([os.path.join(self.get_active_save_dir(), t) for t in titles])
                        self.entry_out_filename.delete(0, tk.END)
                        self.entry_out_filename.insert(0, out_fname)

                    out_fname = re.sub(r'[\\/*?:"<>|]', "_", out_fname).strip()
                    
                    out_base_dir = self.entry_out_dir.get().strip() or self.my_doc_dir
                    target_chat_folder = os.path.join(out_base_dir, out_fname)
                    os.makedirs(target_chat_folder, exist_ok=True)

                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    raw_md_lines = [
                        "---",
                        'ai_service: "AiReAnchorForge"',
                        f'created_at: "{now_str}"',
                        f'references: {json.dumps(titles, ensure_ascii=False)}',
                        f'true_start_time: "{now_str}"',
                        f'true_end_time: "{now_str}"',
                        "---",
                        f"\n# 🔨 Forge合成生データ: {out_fname}\n",
                        f"> ⚓ 合成ソース数: {len(titles)} 件 / 処理モード: {task_label}\n\n",
                        merged_result_md
                    ]
                    raw_master_path = os.path.join(target_chat_folder, "raw_master.md")
                    with open(raw_master_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(raw_md_lines))

                    summary_md_lines = [
                        "---",
                        'ai_service: "AiReAnchorForge"',
                        f'created_at: "{now_str}"',
                        f'true_start_time: "{now_str}"',
                        f'true_end_time: "{now_str}"',
                        "---",
                        f"\n# 📝 要約・Forge合成成果物: {out_fname}\n",
                        f"## 📌 概要 (Short Summary)\n{merged_result_md}\n"
                    ]
                    summary_path = os.path.join(target_chat_folder, f"summary_{out_fname}.md")
                    with open(summary_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(summary_md_lines))

                    render_rich_markdown(
                        text_widget=self.forge_preview_text,
                        raw_text="\n".join(raw_md_lines),
                        base_dir=target_chat_folder,
                        show_rich=True,
                        show_images=True,
                        image_refs_list=self.image_refs,
                        filepath=raw_master_path,
                        show_style="rich_md"
                    )

                    messagebox.showinfo(
                        "合成完了", 
                        f"統合チャットフォルダ 『{out_fname}』 を my_forge 配下に正常作成しました！\n\n"
                        f"・生データ: raw_master.md\n"
                        f"・サマリー: summary_{out_fname}.md\n\n"
                        f"ポータル画面に戻ると『🔨 my_forge』の配下にチャットとして表示されます。"
                    )

                    if self.main_app and hasattr(self.main_app, "refresh_portal_data"):
                        self.main_app.refresh_portal_data()

                else:
                    messagebox.showerror("エラー", f"AI合成失敗:\n{res}")

            self.after(0, gui_update)

        threading.Thread(target=thread_task, daemon=True).start()


# ================= 🖥️ 単体起動時テストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("🔨 AiReAnchorForge - テストワークスペース (マルチスレッド爆速スキャン対応版)")
    root.geometry("1100x700")

    if os.path.exists(ICON_PORTAL):
        try: root.iconbitmap(ICON_PORTAL)
        except: pass

    forge_frame = AiReAnchorForgeFrame(root)
    forge_frame.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()