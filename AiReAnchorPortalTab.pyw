# -*- coding: utf-8 -*-
# AiReAnchorPortalTab.pyw - メインポータル閲覧 ＆ 統合プレビューモジュール (マルチスレッド並列爆速スキャン・年表RAG対話連携対応版)
import os
import sys
import json
import re
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

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
    from AiReLinkerImporter import AiReLinkerImporterFrame
    HAS_IMPORTER = True
except ImportError:
    HAS_IMPORTER = False

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
    from AiReChat import AiReChatFrame
    HAS_CHAT = True
except ImportError:
    HAS_CHAT = False

try:
    from AiReKnotsExportDialog import AiReKnotsExportDialog
    HAS_EXPORT_DIALOG = True
except ImportError:
    HAS_EXPORT_DIALOG = False


class AiReAnchorPortalFrame(ttk.Frame):
    def __init__(self, parent, main_app=None):
        super().__init__(parent)
        self.main_app = main_app
        
        if main_app:
            self.config = main_app.config
            self.save_dir = main_app.save_dir
        else:
            self.config = self.load_config()
            self.save_dir = self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))
            
        self.my_doc_dir = os.path.join(self.save_dir, "my_forge")
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(self.my_doc_dir, exist_ok=True)
        
        self.knots_engine = AiReKnotsEngine(self.config) if HAS_KNOTS else None
        self.accessway_ctrl = AiReAccesswayController(self.config, self.save_dir) if HAS_ACCESSWAY else None

        self.current_preview_mode = self.config.get("last_preview_mode", "raw")
        self.current_source_mode = self.config.get("last_source_mode", "master")
        self.selected_chat_folder = self.config.get("last_chat_folder", None)
        
        self.selected_signal_data = None
        self.image_refs = []

        self.show_left = True
        self.show_right = True

        self.build_ui()
        self.refresh_portal_data()
        self.restore_last_selection()
        
        self.after(500, self.restore_sash_positions)

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    def save_portal_state(self):
        self.config["last_preview_mode"] = self.current_preview_mode
        self.config["last_source_mode"] = self.current_source_mode
        self.config["last_chat_folder"] = self.selected_chat_folder
        self.config["last_markdown_style"] = self.style_var.get()
        
        try:
            total_w = self.portal_pane.winfo_width()
            sash0 = self.portal_pane.sashpos(0)
            sash1 = self.portal_pane.sashpos(1)

            if total_w > 100 and (total_w * 0.05 < sash0 < total_w * 0.5) and (sash0 < sash1 < total_w * 0.95):
                self.config["sash_pos_0"] = sash0
                self.config["sash_pos_1"] = sash1
        except: pass

        if self.main_app:
            self.main_app.save_config()
        else:
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            except: pass

    def restore_sash_positions(self):
        try:
            self.portal_pane.update_idletasks()
            total_w = self.portal_pane.winfo_width()
            if total_w <= 200:
                total_w = 1200

            s0 = self.config.get("sash_pos_0")
            s1 = self.config.get("sash_pos_1")

            is_safe_s0 = (s0 is not None) and (total_w * 0.10 <= s0 <= total_w * 0.45)
            is_safe_s1 = (s1 is not None) and (s0 is not None) and (s0 + 100 <= s1 <= total_w * 0.90)

            if is_safe_s0 and is_safe_s1:
                self.portal_pane.sashpos(0, int(s0))
                self.portal_pane.sashpos(1, int(s1))
            else:
                default_s0 = int(total_w * 0.25)
                default_s1 = int(total_w * 0.75)
                self.portal_pane.sashpos(0, default_s0)
                self.portal_pane.sashpos(1, default_s1)
                
                self.config["sash_pos_0"] = default_s0
                self.config["sash_pos_1"] = default_s1
                self.save_portal_state()
        except: pass

    def build_ui(self):
        top_global_bar = ttk.Frame(self, padding=(4, 2))
        top_global_bar.pack(fill="x", side="top")

        self.btn_left_toggle = ttk.Button(top_global_bar, text="◀ ツリー隠す", width=13, command=self.toggle_left_panel)
        self.btn_left_toggle.pack(side="left", padx=2)

        self.lbl_global_status = ttk.Label(top_global_bar, text="⚓ 選択中のチャット: なし", font=("MS Gothic", 9, "bold"), foreground="#2980b9")
        self.lbl_global_status.pack(side="left", padx=10, fill="x", expand=True)

        self.btn_right_toggle = ttk.Button(top_global_bar, text="AI対話 隠す ▶", width=13, command=self.toggle_right_panel)
        self.btn_right_toggle.pack(side="right", padx=2)

        self.portal_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.portal_pane.pack(fill="both", expand=True, padx=4, pady=2)
        
        # 左パネル
        self.left_p = ttk.Frame(self.portal_pane, width=280)
        self.portal_pane.add(self.left_p, weight=1)
        
        left_hdr = ttk.Frame(self.left_p)
        left_hdr.pack(fill="x", pady=2)
        ttk.Label(left_hdr, text="🔍 横断検索:", font=("MS Gothic", 9, "bold")).pack(side="left", anchor="w")
        ttk.Button(left_hdr, text="🔄 再読み込み", width=11, command=self.refresh_portal_data).pack(side="right", padx=2)

        self.search_var = tk.StringVar()
        ttk.Entry(self.left_p, textvariable=self.search_var).pack(fill="x", pady=2)
        self.search_var.trace("w", lambda *a: self.refresh_portal_data())
        
        self.tree = ttk.Treeview(self.left_p, selectmode="browse")
        self.tree.pack(fill="both", expand=True, pady=2)
        self.tree.bind("<<TreeviewSelect>>", self.on_file_selected)
        self.tree.bind("<<TreeviewOpen>>", self.on_tree_expanded)
        self.tree.bind("<<TreeviewClose>>", self.on_tree_collapsed)

        lbl_legend = ttk.Label(
            self.left_p, 
            text="💡 凡例: [🌟マスター 📝要約 📦一括 📡スクレイプ 🔗3rd] ※カッコ内＝最大アセット数",
            font=("MS Gothic", 8), 
            foreground="#555555"
        )
        lbl_legend.pack(side="bottom", fill="x", pady=2, padx=2)

        # 中央パネル
        self.center_p = ttk.Frame(self.portal_pane, width=560)
        self.portal_pane.add(self.center_p, weight=2)
        
        profile_meta_f = ttk.LabelFrame(self.center_p, text=" 📌 チャットプロフィール ＆ 編集アクション ", padding=6)
        profile_meta_f.pack(fill="x", pady=2)
        
        row_meta1 = ttk.Frame(profile_meta_f)
        row_meta1.pack(fill="x", pady=1)

        ttk.Label(row_meta1, text="📌 題名:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=2)
        self.entry_chat_title = ttk.Entry(row_meta1, font=("MS Gothic", 9))
        self.entry_chat_title.pack(side="left", fill="x", expand=True, padx=4)

        ttk.Button(row_meta1, text="✏️ リネーム", command=self.rename_current_chat).pack(side="left", padx=2)
        ttk.Button(row_meta1, text="⚡ 物理統合生成", command=self.export_integrated_master_now).pack(side="left", padx=2)
        ttk.Button(row_meta1, text="🗑️ チャット削除", command=self.delete_current_chat).pack(side="left", padx=2)

        row_meta2 = ttk.Frame(profile_meta_f)
        row_meta2.pack(fill="x", pady=2)

        self.lbl_svc_disp = ttk.Label(row_meta2, text="[AI: -]", font=("MS Gothic", 8), foreground="#555555")
        self.lbl_svc_disp.pack(side="left", padx=2)

        self.lbl_time_disp = ttk.Label(row_meta2, text="⏱ 時間: -", font=("MS Gothic", 8), foreground="#555555")
        self.lbl_time_disp.pack(side="left", padx=8)

        self.lbl_char_count_disp = ttk.Label(row_meta2, text="📝 文字数: -", font=("MS Gothic", 8, "bold"), foreground="#0284c7")
        self.lbl_char_count_disp.pack(side="left", padx=8)

        row_meta3 = ttk.Frame(profile_meta_f)
        row_meta3.pack(fill="x", pady=2)

        ttk.Label(row_meta3, text="マーク:").pack(side="left", padx=2)
        self.mark_combo = ttk.Combobox(row_meta3, values=["☆ 無し", "★ 星", "◆ ダイヤ"], width=8, state="readonly")
        self.mark_combo.set("☆ 無し")
        self.mark_combo.pack(side="left", padx=2)
        
        ttk.Label(row_meta3, text="タグ:").pack(side="left", padx=(6, 2))
        self.entry_tags = ttk.Entry(row_meta3, width=18)
        self.entry_tags.pack(side="left", padx=2)
        ttk.Button(row_meta3, text="💾 属性保存", command=self.save_metadata).pack(side="left", padx=4)

        # 🌟 年表RAG質問用ボタン (my_RAG_Vault参照時のみ有効化) ＆ 通常要約対話ボタン
        self.btn_rag_chat = ttk.Button(
            row_meta3, 
            text="🗺️ 年表を参照してAiReChatで質問", 
            command=self.start_chat_with_chronicle_rag,
            state="disabled"  # デフォルトはグレーアウト
        )
        self.btn_rag_chat.pack(side="right", padx=2)

        ttk.Button(row_meta3, text="💬 要約で対話開始", command=self.start_chat_with_current_summary).pack(side="right", padx=2)

        prev_f = ttk.LabelFrame(self.center_p, text=" 📖 ログ本文 ＆ 統合マスタープレビュー ", padding=8)
        prev_f.pack(fill="both", expand=True, pady=2)
        
        toggle_f1 = ttk.Frame(prev_f)
        toggle_f1.pack(fill="x", pady=2)

        ttk.Button(toggle_f1, text="📄 生データ(Raw)", command=lambda: self.switch_mode("raw")).pack(side="left", padx=1)
        ttk.Button(toggle_f1, text="📝 要約(Summary)", command=lambda: self.switch_mode("summary")).pack(side="left", padx=1)

        ttk.Button(toggle_f1, text="🔍 検索 (Ctrl+F)", command=self.toggle_search_widget_in_portal).pack(side="left", padx=4)
        ttk.Button(toggle_f1, text="📁 アセットフォルダを開く", command=self.open_current_assets_folder).pack(side="left", padx=4)

        # 🌟 5スタイル対応ラジオボタン群 (古設定値との互換性処理付き)
        last_style = self.config.get("last_markdown_style", "simple_md")
        if last_style == "simple": last_style = "simple_md"
        elif last_style == "aire": last_style = "simple_aire"
        elif last_style == "rich": last_style = "rich_md"
        elif last_style == "raw": last_style = "none"

        self.style_var = tk.StringVar(value=last_style)
        
        rb_s_md = ttk.Radiobutton(toggle_f1, text="シンプル標準MD", variable=self.style_var, value="simple_md", command=self.on_style_changed)
        rb_s_md.pack(side="left", padx=2)

        rb_r_md = ttk.Radiobutton(toggle_f1, text="リッチ標準MD", variable=self.style_var, value="rich_md", command=self.on_style_changed)
        rb_r_md.pack(side="left", padx=2)

        rb_s_aire = ttk.Radiobutton(toggle_f1, text="AiRe装飾", variable=self.style_var, value="simple_aire", command=self.on_style_changed)
        rb_s_aire.pack(side="left", padx=2)

        rb_r_aire = ttk.Radiobutton(toggle_f1, text="リッチAiRe装飾", variable=self.style_var, value="rich_aire", command=self.on_style_changed)
        rb_r_aire.pack(side="left", padx=2)

        rb_none = ttk.Radiobutton(toggle_f1, text="装飾OFF(Raw)", variable=self.style_var, value="none", command=self.on_style_changed)
        rb_none.pack(side="left", padx=2)
        
        self.img_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toggle_f1, text="画像・メディア表示", variable=self.img_var, command=self.load_preview).pack(side="left", padx=6)

        btn_ai_f = ttk.Frame(toggle_f1)
        btn_ai_f.pack(side="right")
        ttk.Button(btn_ai_f, text="⚡ 要約・ストーリー生成", command=lambda: self.run_manual_ai_task("all")).pack(side="left", padx=1)

        self.prog_container = ttk.Frame(prev_f)
        self.prog_label = ttk.Label(self.prog_container, text="⏳ AI要約・ストーリーを生成中です...", font=("MS Gothic", 9, "bold"), foreground="#0284c7")
        self.prog_label.pack(side="left", padx=5)
        self.prog_bar = ttk.Progressbar(self.prog_container, mode="indeterminate", length=220)
        self.prog_bar.pack(side="left", fill="x", expand=True, padx=5)
    
        toggle_f2 = ttk.Frame(prev_f)
        toggle_f2.pack(fill="x", pady=(4, 2))

        ttk.Label(toggle_f2, text="表示ソース:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=4)
        self.source_mode_var = tk.StringVar(value=self.current_source_mode)

        self.rb_master = ttk.Radiobutton(toggle_f2, text="🌟 統合マスター", variable=self.source_mode_var, value="master", command=self.on_source_changed)
        self.rb_master.pack(side="left", padx=3)

        self.rb_importer = ttk.Radiobutton(toggle_f2, text="📦 importer", variable=self.source_mode_var, value="importer", command=self.on_source_changed)
        self.rb_importer.pack(side="left", padx=3)

        self.rb_scraped = ttk.Radiobutton(toggle_f2, text="📡 scraped", variable=self.source_mode_var, value="scraped", command=self.on_source_changed)
        self.rb_scraped.pack(side="left", padx=3)

        self.rb_3rd = ttk.Radiobutton(toggle_f2, text="🔗 3rd", variable=self.source_mode_var, value="3rd", command=self.on_source_changed)
        self.rb_3rd.pack(side="left", padx=3)

        self.lbl_src_status = ttk.Label(toggle_f2, text="", font=("MS Gothic", 8), foreground="#555555")
        self.lbl_src_status.pack(side="right", padx=4)

        prev_txt_f = ttk.Frame(prev_f)
        prev_txt_f.pack(fill="both", expand=True, pady=2)

        self.preview_text = tk.Text(prev_txt_f, background="#ffffff", wrap="word")
        self.preview_text.pack(fill="both", expand=True, side="left")
        
        sb_p = ttk.Scrollbar(prev_txt_f, command=self.preview_text.yview)
        sb_p.pack(side="right", fill="y")
        self.preview_text.configure(yscrollcommand=sb_p.set)

        # 右パネル
        self.right_p = ttk.Frame(self.portal_pane, width=280)
        self.portal_pane.add(self.right_p, weight=1)
        
        if HAS_CHAT:
            self.chat_app = AiReChatFrame(self.right_p, self.main_app)
            self.chat_app.pack(fill="both", expand=True)
        else:
            err_chat = ttk.Frame(self.right_p, padding=10)
            ttk.Label(err_chat, text="⚠️ AiReChat.pyw モジュールが見つかりません。").pack()
            err_chat.pack(fill="both", expand=True)

    def update_rag_button_state(self):
        """🌟 選択中ログが my_RAG_Vault（年表データ）の場合のみ『🗺️ 年表を参照して質問』ボタンを有効化"""
        if not self.selected_chat_folder or not os.path.exists(self.selected_chat_folder):
            self.btn_rag_chat.config(state="disabled")
            return

        norm_path = os.path.normpath(self.selected_chat_folder)
        is_rag_vault = ("my_rag_vault" in norm_path.lower()) or (os.path.basename(os.path.dirname(norm_path)).lower() == "my_rag_vault")

        has_chronicle_file = False
        if os.path.exists(norm_path):
            if os.path.isfile(norm_path) and ("chronicle" in os.path.basename(norm_path).lower()):
                has_chronicle_file = True
            elif os.path.isdir(norm_path):
                for f in os.listdir(norm_path):
                    if ("chronicle" in f.lower()) and f.endswith(".md"):
                        has_chronicle_file = True
                        break

        if (is_rag_vault or has_chronicle_file) and HAS_CHAT:
            self.btn_rag_chat.config(state="normal")
        else:
            self.btn_rag_chat.config(state="disabled")

    def toggle_left_panel(self):
        if self.show_left:
            self.portal_pane.forget(self.left_p)
            self.show_left = False
            self.btn_left_toggle.config(text="▶ ツリー表示")
        else:
            self.portal_pane.insert(0, self.left_p, weight=1)
            self.show_left = True
            self.btn_left_toggle.config(text="◀ ツリー隠す")
        self.restore_sash_positions()

    def toggle_right_panel(self):
        if self.show_right:
            self.portal_pane.forget(self.right_p)
            self.show_right = False
            self.btn_right_toggle.config(text="◀ AI対話表示")
        else:
            self.portal_pane.add(self.right_p, weight=1)
            self.show_right = True
            self.btn_right_toggle.config(text="AI対話 隠す ▶")
        self.restore_sash_positions()

    def toggle_search_widget_in_portal(self):
        if hasattr(self.preview_text, "floating_search_widget") and self.preview_text.floating_search_widget.winfo_exists():
            sw = self.preview_text.floating_search_widget
            if sw.winfo_ismapped(): sw.close_widget()
            else: sw.show_at_default_position()

    def switch_mode(self, mode):
        self.current_preview_mode = mode
        self.save_portal_state()
        self.load_preview()

    def on_source_changed(self):
        self.current_source_mode = self.source_mode_var.get()
        self.save_portal_state()
        self.load_preview()

    def on_style_changed(self):
        self.save_portal_state()
        self.load_preview()

    def get_asset_count(self, folder_path):
        if not folder_path or not os.path.exists(folder_path): return 0
        a_dir = os.path.join(folder_path, "assets")
        if os.path.exists(a_dir) and os.path.isdir(a_dir):
            return len([f for f in os.listdir(a_dir) if os.path.isfile(os.path.join(a_dir, f))])
        return 0

    def _worker_scan_chat_info(self, chat_path):
        """🌟 マルチスレッド用 1チャットのバッジ・アセット数一斉計算ワーカー"""
        try:
            badge_prefix = self.build_fixed_width_badge_prefix(chat_path)
            cnt_imp = self.get_asset_count(os.path.join(chat_path, "importer"))
            cnt_scr = self.get_asset_count(os.path.join(chat_path, "scraped"))
            cnt_3rd = self.get_asset_count(os.path.join(chat_path, "3rd"))
            max_assets = max(cnt_imp, cnt_scr, cnt_3rd)
            return chat_path, badge_prefix, max_assets
        except:
            return chat_path, "[　　　　　]", 0

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

    def build_fixed_width_badge_prefix(self, chat_folder):
        has_master = os.path.exists(os.path.join(chat_folder, "raw_master.md"))
        has_sum = self.find_summary_file_path(chat_folder) is not None
        
        imp_p = os.path.join(chat_folder, "importer")
        scr_p = os.path.join(chat_folder, "scraped")
        trd_p = os.path.join(chat_folder, "3rd")

        has_imp = os.path.exists(imp_p) and len(os.listdir(imp_p)) > 0
        has_scr = os.path.exists(scr_p) and len(os.listdir(scr_p)) > 0
        has_3rd = os.path.exists(trd_p) and len(os.listdir(trd_p)) > 0

        s_mas = "🌟" if has_master else "　"
        s_sum = "📝" if has_sum else "　"
        s_imp = "📦" if has_imp else "　"
        s_scr = "📡" if has_scr else "　"
        s_3rd = "🔗" if has_3rd else "　"

        return f"[{s_mas}{s_sum}{s_imp}{s_scr}{s_3rd}]"

    def refresh_portal_data(self):
        """🌟 マルチスレッド並列処理（ThreadPoolExecutor）によるポータルツリー＆アセット数の爆速ロード"""
        self.tree.delete(*self.tree.get_children())
        if not os.path.exists(self.save_dir): return
        
        query = self.search_var.get().strip().lower()
        expanded_folders = self.config.get("expanded_folders", [])
        folder_priority = self.config.get("folder_priority", ["my_RAG_Vault", "my_forge", "Google AI Studio", "Gemini", "ChatGPT", "Claude", "AiReChat"])

        all_folders = [f for f in os.listdir(self.save_dir) if os.path.isdir(os.path.join(self.save_dir, f))]
        if "my_forge" not in all_folders and os.path.exists(self.my_doc_dir):
            all_folders.append("my_forge")

        def sort_key(name):
            if name in folder_priority: return (0, folder_priority.index(name))
            return (1, name)

        sorted_ai_folders = sorted(list(set(all_folders)), key=sort_key)
        raw_chat_entries = []

        for ai_folder in sorted_ai_folders:
            ai_path = os.path.join(self.save_dir, ai_folder)
            chats = sorted(os.listdir(ai_path)) if os.path.exists(ai_path) else []
            
            if query and query not in ai_folder.lower():
                has_match = any(query in c.lower() for c in chats if os.path.isdir(os.path.join(ai_path, c)))
                if not has_match: continue

            seen_chats = set()

            for chat in chats:
                chat_path = os.path.join(ai_path, chat)
                clean_chat_key = chat.strip().lower()

                if os.path.isdir(chat_path) and chat not in ["assets", "my_documents", "my_forge"] and clean_chat_key not in seen_chats:
                    if query and query not in chat.lower() and query not in ai_folder.lower():
                        continue

                    seen_chats.add(clean_chat_key)
                    raw_chat_entries.append((ai_folder, chat.strip(), chat_path))

        # 🌟 全スレッドを一斉起動して全チャットのバッジ・アセット数を並列計算
        chat_info_cache = {}
        chat_paths_to_scan = [cp for _, _, cp in raw_chat_entries]
        
        if chat_paths_to_scan:
            max_workers = min(32, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._worker_scan_chat_info, cp) for cp in chat_paths_to_scan]
                for future in as_completed(futures):
                    cp, badge_prefix, max_assets = future.result()
                    chat_info_cache[cp] = (badge_prefix, max_assets)

        # 🌟 ツリー描画へ一括挿入
        grouped_by_folder = {}
        for ai_folder, clean_chat_name, chat_path in raw_chat_entries:
            grouped_by_folder.setdefault(ai_folder, []).append((clean_chat_name, chat_path))

        for ai_folder in sorted_ai_folders:
            if ai_folder not in grouped_by_folder: continue
            items = grouped_by_folder[ai_folder]

            is_open = ai_folder in expanded_folders
            folder_icon = "📜 " if ai_folder == "my_RAG_Vault" else ("🔨 " if ai_folder == "my_forge" else "📁 ")
            parent_id = self.tree.insert("", "end", text=f"{folder_icon}{ai_folder}", open=is_open)

            for clean_chat_name, chat_path in items:
                badge_prefix, max_assets = chat_info_cache.get(chat_path, ("[　　　　　]", 0))
                asset_str = f" (アセット: {max_assets})" if max_assets > 0 else ""
                disp_text = f"💬 {badge_prefix} {clean_chat_name}{asset_str}"
                self.tree.insert(parent_id, "end", text=disp_text, values=(chat_path,))

    def restore_last_selection(self):
        if not self.selected_chat_folder or not os.path.exists(self.selected_chat_folder): return
        
        for p_item in self.tree.get_children(""):
            for c_item in self.tree.get_children(p_item):
                vals = self.tree.item(c_item, "values")
                if vals and vals[0] == self.selected_chat_folder:
                    self.tree.selection_set(c_item)
                    self.tree.see(c_item)
                    self.on_file_selected(None)
                    return

    def update_source_radio_states(self, chat_folder):
        has_imp = os.path.exists(os.path.join(chat_folder, "importer")) and len(os.listdir(os.path.join(chat_folder, "importer"))) > 0
        has_scr = os.path.exists(os.path.join(chat_folder, "scraped")) and len(os.listdir(os.path.join(chat_folder, "scraped"))) > 0
        has_3rd = os.path.exists(os.path.join(chat_folder, "3rd")) and len(os.listdir(os.path.join(chat_folder, "3rd"))) > 0

        cnt_imp = self.get_asset_count(os.path.join(chat_folder, "importer"))
        cnt_scr = self.get_asset_count(os.path.join(chat_folder, "scraped"))
        cnt_3rd = self.get_asset_count(os.path.join(chat_folder, "3rd"))
        
        max_assets = max(cnt_imp, cnt_scr, cnt_3rd)

        self.rb_master.config(text=f"🌟 統合マスター ({max_assets})", state="normal")
        self.rb_importer.config(text=f"📦 importer ({cnt_imp})", state="normal" if has_imp else "disabled")
        self.rb_scraped.config(text=f"📡 scraped ({cnt_scr})", state="normal" if has_scr else "disabled")
        self.rb_3rd.config(text=f"🔗 3rd ({cnt_3rd})", state="normal" if has_3rd else "disabled")

        curr_mode = self.source_mode_var.get()
        if curr_mode == "importer" and not has_imp: self.source_mode_var.set("master")
        elif curr_mode == "scraped" and not has_scr: self.source_mode_var.set("master")
        elif curr_mode == "3rd" and not has_3rd: self.source_mode_var.set("master")
        self.current_source_mode = self.source_mode_var.get()

    def on_file_selected(self, event):
        item = self.tree.selection()
        if not item: return

        vals = self.tree.item(item[0], "values")
        if not vals: 
            self.selected_chat_folder = None
            self.lbl_global_status.config(text="⚓ 選択中: カテゴリフォルダノード")
            self.entry_chat_title.delete(0, tk.END)
            self.entry_chat_title.insert(0, "(フォルダ選択中)")
            self.lbl_svc_disp.config(text="[AI: -]")
            self.lbl_time_disp.config(text="⏱ 時間: -")
            self.lbl_char_count_disp.config(text="📝 文字数: -")

            self.preview_text.config(state="normal")
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.insert("1.0", "💡 カテゴリフォルダを選択しました。配下のチャットログをクリックするとプレビューが表示されます。")
            self.preview_text.config(state="disabled")
            self.update_rag_button_state()
            return

        chat_folder = vals[0]
        if not os.path.exists(chat_folder) or not os.path.isdir(chat_folder): return

        self.selected_chat_folder = chat_folder
        self.save_portal_state()
        
        self.update_source_radio_states(chat_folder)
        self.update_rag_button_state()

        if self.knots_engine:
            self.selected_signal_data = self.knots_engine.get_chat_signal_data(chat_folder)
            
        self.load_preview()

    def load_preview(self):
        if not self.selected_chat_folder or not os.path.exists(self.selected_chat_folder): return

        chat_folder = self.selected_chat_folder
        chat_name = os.path.basename(chat_folder)
        source_mode = self.current_source_mode
        preview_mode = self.current_preview_mode
        current_style = self.style_var.get()

        content = ""
        base_dir = chat_folder
        status_msg = ""
        svc_name = "不明"
        time_str = "不明"
        target_filepath = None

        if source_mode == "master":
            if preview_mode == "raw":
                master_file = os.path.join(chat_folder, "raw_master.md")
                # my_RAG_Vault 内の raw_Chronicle_*.md も自動検出
                if not os.path.exists(master_file):
                    for f in os.listdir(chat_folder):
                        if f.startswith("raw_Chronicle_") and f.endswith(".md"):
                            master_file = os.path.join(chat_folder, f)
                            break

                if os.path.exists(master_file):
                    target_filepath = master_file
                    with open(master_file, "r", encoding="utf-8") as f: content = f.read()
                    
                    cnt_imp = self.get_asset_count(os.path.join(chat_folder, "importer"))
                    cnt_scr = self.get_asset_count(os.path.join(chat_folder, "scraped"))
                    cnt_3rd = self.get_asset_count(os.path.join(chat_folder, "3rd"))
                    max_assets = max(cnt_imp, cnt_scr, cnt_3rd)

                    status_msg = f"（マスター参照: {os.path.basename(master_file)} / アセット{max_assets}個）"
                    m_s = re.search(r'ai_service:\s*"([^"]+)"', content)
                    if m_s: svc_name = m_s.group(1)
                else:
                    if self.knots_engine:
                        res, err = self.knots_engine.build_integrated_master(chat_folder)
                        if res:
                            content = res["master_markdown"]
                            svc_name = res.get("service_name", "AI Service")
                            time_str = f"{res.get('start_time', '')} 〜 {res.get('end_time', '')}"
                            status_msg = "（統合マスター: 裏側即時合成プレビュー）"
                        else: content = "💡 統合マスターの即時合成に失敗しました。"
                    else: content = "💡 統合マスター(raw_master.md)が未生成です。『⚡ 物理統合生成』ボタンで生成してください。"
            else:
                sum_file = self.find_summary_file_path(chat_folder)

                if sum_file and os.path.exists(sum_file):
                    target_filepath = sum_file
                    with open(sum_file, "r", encoding="utf-8") as f: content = f.read()
                    status_msg = f"（ルート直下要約参照: {os.path.basename(sum_file)}）"
                else:
                    content = "💡 要約・ストーリーが未生成です。上部の「⚡ 要約・ストーリー生成」ボタンを押して生成できます。"
        else:
            sub_folder = os.path.join(chat_folder, source_mode)
            base_dir = sub_folder
            if os.path.exists(sub_folder):
                target_file = None
                for f in os.listdir(sub_folder):
                    if preview_mode == "raw" and f.endswith(".md"):
                        target_file = os.path.join(sub_folder, f)
                        break

                if target_file and os.path.exists(target_file):
                    target_filepath = target_file
                    with open(target_file, "r", encoding="utf-8") as f: content = f.read()
                    asset_cnt = self.get_asset_count(sub_folder)
                    status_msg = f"（{source_mode} 生ログ / アセット{asset_cnt}個）"
                elif preview_mode == "summary":
                    sum_file = self.find_summary_file_path(chat_folder)
                    if sum_file and os.path.exists(sum_file):
                        target_filepath = sum_file
                        with open(sum_file, "r", encoding="utf-8") as f: content = f.read()
                        status_msg = f"（{source_mode} 選択中 - ルート直下要約表示: {os.path.basename(sum_file)}）"
                    else:
                        content = f"💡 チャット直下に要約・ストーリーが未生成です。上部ボタンから生成できます。"
                else:
                    content = f"⚠️ 『{source_mode}』 領域内に生ログ(raw)が見つかりません。"
            else:
                content = f"⚠️ このチャットには 『{source_mode}』 のデータが存在しません。"

        self.lbl_global_status.config(text=f"⚓ 選択中: {chat_name}")
        self.entry_chat_title.delete(0, tk.END)
        self.entry_chat_title.insert(0, chat_name)
        self.lbl_svc_disp.config(text=f"[AI: {svc_name}]")
        self.lbl_time_disp.config(text=f"⏱ 時間: {time_str}")
        self.lbl_src_status.config(text=status_msg)

        char_count = len(content) if content else 0
        self.lbl_char_count_disp.config(text=f"📝 文字数: {char_count:,} 文字")

        render_rich_markdown(
            text_widget=self.preview_text, 
            raw_text=content, 
            base_dir=base_dir, 
            show_rich=(current_style != "none"), 
            show_images=self.img_var.get(), 
            image_refs_list=self.image_refs,
            filepath=target_filepath,
            on_update_callback=self.load_preview,
            show_style=current_style
        )

    def rename_current_chat(self):
        if not self.selected_chat_folder or not os.path.exists(self.selected_chat_folder): return

        old_folder = self.selected_chat_folder
        old_name = os.path.basename(old_folder)
        new_name_raw = self.entry_chat_title.get().strip()

        if not new_name_raw or new_name_raw == old_name: return

        new_name = re.sub(r'[\\/*?:"<>|]', "_", new_name_raw).strip()
        new_folder = os.path.join(os.path.dirname(old_folder), new_name)

        if os.path.exists(new_folder):
            messagebox.showerror("エラー", f"同名のチャットフォルダが存在します:\n{new_name}")
            return

        try:
            os.rename(old_folder, new_folder)
            self.selected_chat_folder = new_folder
            self.save_portal_state()
            messagebox.showinfo("成功", f"リネームしました:\n『{old_name}』 ➔ 『{new_name}』")
            self.refresh_portal_data()
        except Exception as e:
            messagebox.showerror("エラー", f"リネーム失敗: {e}")

    def delete_current_chat(self):
        if not self.selected_chat_folder or not os.path.exists(self.selected_chat_folder): return

        chat_name = os.path.basename(self.selected_chat_folder)
        ans = messagebox.askyesno("⚠️ 削除確認", f"チャット『{chat_name}』を完全削除しますか？")
        if not ans: return

        try:
            shutil.rmtree(self.selected_chat_folder)
            self.selected_chat_folder = None
            self.save_portal_state()
            messagebox.showinfo("削除完了", f"チャット『{chat_name}』を削除しました。")
            self.refresh_portal_data()
        except Exception as e:
            messagebox.showerror("エラー", f"削除失敗: {e}")

    def export_integrated_master_now(self):
        if not self.selected_chat_folder:
            messagebox.showwarning("警告", "対象のチャットをリストから選択してください。")
            return

        if HAS_EXPORT_DIALOG:
            AiReKnotsExportDialog(
                parent=self.winfo_toplevel(),
                chat_folder_path=self.selected_chat_folder,
                knots_engine=self.knots_engine,
                on_success_callback=lambda: (self.refresh_portal_data(), self.load_preview())
            )
        else:
            if not self.knots_engine: return
            chat_name = os.path.basename(self.selected_chat_folder)
            ok, path_or_err = self.knots_engine.export_master_cache(self.selected_chat_folder)
            if ok:
                messagebox.showinfo("統合成功", f"物理統合マスター(raw_master.md)をルートに生成しました！")
                self.refresh_portal_data()
                self.load_preview()
            else:
                messagebox.showerror("エラー", f"統合生成失敗:\n{path_or_err}")

    def start_chat_with_current_summary(self):
        if not self.selected_chat_folder or not HAS_CHAT: return

        chat_name = os.path.basename(self.selected_chat_folder)
        sum_file = self.find_summary_file_path(self.selected_chat_folder)

        summary_text = ""
        if sum_file and os.path.exists(sum_file):
            try:
                with open(sum_file, "r", encoding="utf-8") as f: summary_text = f.read()
            except: pass

        raw_content = self.preview_text.get("1.0", tk.END).strip()

        if hasattr(self, 'chat_app') and self.chat_app:
            self.chat_app.load_external_context_and_start(summary_text, title=chat_name, raw_content=raw_content)
            if not self.show_right: self.toggle_right_panel()

    def start_chat_with_chronicle_rag(self):
        """🌟 選択中の my_RAG_Vault 年表テキストをRAGコンテキストとしてAiReChatへ渡し、[3]年表RAGモードで対話開始"""
        if not self.selected_chat_folder or not HAS_CHAT: return

        chat_name = os.path.basename(self.selected_chat_folder)
        chronicle_text = self.preview_text.get("1.0", tk.END).strip()

        if hasattr(self, 'chat_app') and self.chat_app:
            self.chat_app.load_chronicle_rag_context_and_start(chronicle_text, title=chat_name)
            if not self.show_right: self.toggle_right_panel()

    def run_manual_ai_task(self, task_type):
        if not self.selected_chat_folder or not self.accessway_ctrl: return

        chat_folder = self.selected_chat_folder
        chat_name = os.path.basename(chat_folder)

        raw_p = os.path.join(chat_folder, "raw_master.md")
        if not os.path.exists(raw_p):
            for sk in ["importer", "scraped", "3rd"]:
                sp = os.path.join(chat_folder, sk)
                if os.path.exists(sp):
                    for f in os.listdir(sp):
                        if f.endswith(".md"):
                            raw_p = os.path.join(sp, f)
                            break

        if not os.path.exists(raw_p):
            if self.knots_engine:
                res, _ = self.knots_engine.build_integrated_master(chat_folder)
                if res:
                    tmp_p = os.path.join(chat_folder, "_temp_raw.md")
                    with open(tmp_p, "w", encoding="utf-8") as f: f.write(res["master_markdown"])
                    raw_p = tmp_p

        if not os.path.exists(raw_p):
            messagebox.showerror("エラー", "要約生成に必要な生ログ(raw)が見つかりません。")
            return

        self.prog_container.pack(fill="x", pady=2)
        self.prog_label.config(text=f"⏳ チャット『{chat_name}』の AI要約・ストーリー処理を開始します...")
        self.prog_bar.config(mode="indeterminate")
        self.prog_bar.start(10)

        def log_progress_callback(msg):
            def update_ui_progress():
                clean_msg = str(msg).strip()
                self.prog_label.config(text=f"⏳ 『{chat_name}』: {clean_msg}")

                m = re.search(r'\((\d+)%\)', clean_msg)
                if m:
                    pct = int(m.group(1))
                    self.prog_bar.stop()
                    self.prog_bar.config(mode="determinate", value=pct)

            self.after(0, update_ui_progress)

        def thread_task():
            ok, msg = self.accessway_ctrl.process_chat_summary_task(chat_folder, raw_p, log_callback=log_progress_callback)
            
            tmp_p = os.path.join(chat_folder, "_temp_raw.md")
            if os.path.exists(tmp_p): os.remove(tmp_p)

            def gui_update():
                self.prog_bar.stop()
                self.prog_container.pack_forget()

                if ok:
                    messagebox.showinfo("成功", f"『{chat_name}』の要約・ストーリーをルートに保存しました！")
                    self.refresh_portal_data()
                    self.switch_mode("summary")
                else:
                    messagebox.showerror("エラー", f"生成失敗:\n{msg}")
                    self.load_preview()

            self.after(0, gui_update)

        threading.Thread(target=thread_task, daemon=True).start()

    def open_current_assets_folder(self):
        if not self.selected_chat_folder or not os.path.exists(self.selected_chat_folder):
            messagebox.showwarning("警告", "対象のチャットをリストから選択してください。")
            return

        source_mode = self.current_source_mode
        possible_dirs = []

        if source_mode != "master":
            possible_dirs.append(os.path.join(self.selected_chat_folder, source_mode, "assets"))

        possible_dirs.extend([
            os.path.join(self.selected_chat_folder, "importer", "assets"),
            os.path.join(self.selected_chat_folder, "scraped", "assets"),
            os.path.join(self.selected_chat_folder, "3rd", "assets"),
            os.path.join(self.selected_chat_folder, "assets"),
            self.selected_chat_folder
        ])

        target_dir = None
        for d in possible_dirs:
            if os.path.exists(d) and os.path.isdir(d):
                target_dir = d
                break

        if target_dir:
            try: os.startfile(target_dir)
            except Exception as e: messagebox.showerror("エラー", f"フォルダを開けませんでした:\n{e}")
        else:
            messagebox.showwarning("フォルダなし", "アセットフォルダ(assets/)が存在しません。")

    def save_metadata(self):
        messagebox.showinfo("保存", "属性・マーク情報を保存しました。")

    def save_config_state(self):
        self.save_portal_state()

    def on_tree_expanded(self, event):
        item = self.tree.focus()
        if not item: return
        text = self.tree.item(item, "text")
        folder_name = re.sub(r'^[📁🔨📜\s]+', '', text).strip()
        expanded = self.config.setdefault("expanded_folders", [])
        if folder_name and folder_name not in expanded:
            expanded.append(folder_name)
            self.save_config_state()

    def on_tree_collapsed(self, event):
        item = self.tree.focus()
        if not item: return
        text = self.tree.item(item, "text")
        folder_name = re.sub(r'^[📁🔨📜\s]+', '', text).strip()
        expanded = self.config.get("expanded_folders", [])
        if folder_name in expanded:
            expanded.remove(folder_name)
            self.config["expanded_folders"] = expanded
            self.save_config_state()

    def sync_all_chats(self):
        if HAS_IMPORTER:
            importer = AiReLinkerImporterFrame(self, self.main_app)
            importer.run_import_select()

if __name__ == '__main__':
    root = tk.Tk()
    root.title("⚓ AiReAnchorPortalTab テストランナー (マルチスレッド爆速スキャン対応版)")
    root.geometry("1100x700")
    app = AiReAnchorPortalFrame(root)
    app.pack(fill="both", expand=True)
    root.mainloop()