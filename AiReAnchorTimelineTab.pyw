# -*- coding: utf-8 -*-
# AiReAnchorTimelineTab.pyw - DTM/DAW風 タイムライン (一括ソートプルダウン ＆ AIグループ切り替え ＆ 動的AIカラーパレット変更対応版)
import os
import sys
import json
import re
import datetime
import unicodedata
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser

# 🌟 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

# 🌟 Windows AppID 登録
try:
    import ctypes
    myappid = 'airelinker.suite.timeline.v9'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


class AiReAnchorTimelineFrame(ttk.Frame):
    """🌟 DTM/DAWスタイルの高精度・高機能タイムライン GUI フレーム"""
    def __init__(self, parent, save_dir=None, ai_colors=None):
        super().__init__(parent)
        self.default_save_dir = save_dir if save_dir else os.path.join(CURRENT_DIR, "logs")
        self.ai_colors = ai_colors if ai_colors else {
            "Google AI Studio": "#3498db",
            "Gemini": "#2ecc71",
            "ChatGPT": "#e74c3c",
            "Claude": "#9b59b6",
            "AiReChat": "#a855f7",
            "Local LLM": "#e67e22"
        }
        
        self.log_data = []
        self.folder_visibility = {}
        self.chat_visibility = {}
        
        # 🌟 超広域〜詳細拡大まで柔軟に対応するズーム初期値
        self.zoom_x = 0.02   # 横軸ズーム初期値 (何年分も俯瞰可能)
        self.zoom_y = 22.0   # 縦軸ズーム初期値 (全チャット一覧表示向け)
        self.text_pos_mode = "left_side" # "on_bar" or "left_side"
        self.group_mode = "split"        # "split" (分ける) or "flat" (分けない)

        # 参照ソース優先順位デフォルト
        self.source_priority = ["master", "importer", "scraped", "3rd"]
        
        self.build_widgets()
        self.refresh_timeline_data()

    def get_active_save_dir(self):
        """config.json から最新の保存先パスを取得"""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    d = cfg.get("save_dir")
                    if d and os.path.exists(d):
                        return d
            except: pass
        return self.default_save_dir

    def set_active_save_dir(self, new_dir):
        """手動選択されたフォルダパスを config.json に保存"""
        if not new_dir or not os.path.exists(new_dir): return
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: cfg = json.load(f)
            except: pass

        cfg["save_dir"] = new_dir
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except: pass

        self.refresh_timeline_data()

    def browse_and_set_save_dir(self):
        curr = self.get_active_save_dir()
        selected = filedialog.askdirectory(title="参照するログフォルダを選択", initialdir=curr if os.path.exists(curr) else CURRENT_DIR)
        if selected:
            self.set_active_save_dir(selected)

    def cycle_source_priority(self):
        """参照ソース優先順位を切り替え"""
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
        self.refresh_timeline_data()

    def update_priority_btn_label(self):
        disp_map = {"master": "🌟マスター", "importer": "📦インポート", "scraped": "📡スクレイプ", "3rd": "🔗3rd"}
        p_str = " ➔ ".join([disp_map.get(k, k) for k in self.source_priority])
        self.btn_priority.config(text=f"🔀 優先順: [ {p_str} ]")

    def build_widgets(self):
        # 1. 最上部コントロールバー
        ctrl_frame = ttk.Frame(self, padding=4)
        ctrl_frame.pack(fill="x", side="top")
        
        ttk.Button(ctrl_frame, text="🔄 再読み込み", command=self.refresh_timeline_data).pack(side="left", padx=2)
        ttk.Button(ctrl_frame, text="📂 参照...", command=self.browse_and_set_save_dir).pack(side="left", padx=2)

        # 参照ソース優先順位切り替えボタン
        self.btn_priority = ttk.Button(ctrl_frame, text="🔀 優先順: [ 🌟マスター ➔ 📦インポート ➔ 📡スクレイプ ➔ 🔗3rd ]", command=self.cycle_source_priority)
        self.btn_priority.pack(side="left", padx=4)

        # 表示一括制御
        ttk.Button(ctrl_frame, text="☑ 全表示", width=7, command=self.show_all_tracks).pack(side="left", padx=(4, 1))
        ttk.Button(ctrl_frame, text="☐ 全非表示", width=7, command=self.hide_all_tracks).pack(side="left", padx=1)

        # トラック順序個別に微調整
        order_f = ttk.Frame(ctrl_frame)
        order_f.pack(side="left", padx=4)
        ttk.Button(order_f, text="▲ 上へ", width=5, command=self.move_item_up).pack(side="left", padx=1)
        ttk.Button(order_f, text="▼ 下へ", width=5, command=self.move_item_down).pack(side="left", padx=1)

        # 🌟 ソート並び替えプルダウン
        sort_f = ttk.Frame(ctrl_frame)
        sort_f.pack(side="left", padx=4)
        
        self.sort_var = tk.StringVar(value="⏱ 開始時間が古い順")
        sort_options = [
            "⏱ 開始時間が古い順",
            "⏱ 開始時間が新しい順",
            "⏱ 終了時間が古い順",
            "⏱ 終了時間が新しい順",
            "🔤 名前順 (A-Z)",
            "🔤 名前順 (Z-A)",
            "🔤 あいうえお順 (昇順)",
            "🔤 あいうえお順 (降順)",
            "⏳ タイムライン（期間）が長い順",
            "⏳ タイムライン（期間）が短い順"
        ]
        self.combo_sort = ttk.Combobox(sort_f, textvariable=self.sort_var, values=sort_options, state="readonly", width=18)
        self.combo_sort.pack(side="left")
        self.combo_sort.bind("<<ComboboxSelected>>", self.on_sort_selected)

        # 🌟 AIグループで分ける／分けない ラジオボタン
        group_f = ttk.LabelFrame(ctrl_frame, text=" AIグループ ", padding=2)
        group_f.pack(side="left", padx=4)
        self.var_group_mode = tk.StringVar(value="split")
        ttk.Radiobutton(group_f, text="分ける", variable=self.var_group_mode, value="split", command=self.on_group_mode_changed).pack(side="left", padx=2)
        ttk.Radiobutton(group_f, text="分けない", variable=self.var_group_mode, value="flat", command=self.on_group_mode_changed).pack(side="left", padx=2)

        # 文字位置モード切り替え
        pos_f = ttk.LabelFrame(ctrl_frame, text=" テキスト位置 ", padding=2)
        pos_f.pack(side="left", padx=4)
        self.var_text_pos = tk.StringVar(value="left_side")
        ttk.Radiobutton(pos_f, text="バーの上", variable=self.var_text_pos, value="on_bar", command=self.on_text_pos_changed).pack(side="left", padx=2)
        ttk.Radiobutton(pos_f, text="バーの左側", variable=self.var_text_pos, value="left_side", command=self.on_text_pos_changed).pack(side="left", padx=2)

        # 🌟 動的AIサービス凡例表示エリア（カラーピッカー連携）
        self.legend_frame = ttk.LabelFrame(ctrl_frame, text=" 🎨 実在するAIサービス (クリックで色変更) ", padding=2)
        self.legend_frame.pack(side="right", padx=4)

        # 2. メイン PanedWindow
        timeline_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        timeline_pane.pack(fill="both", expand=True, padx=4, pady=4)
        
        # 左パネル: トラックリスト
        self.list_frame = ttk.Frame(timeline_pane, width=280)
        timeline_pane.add(self.list_frame, weight=1)

        # 🌟 要望通り「トラックリスト」の1個上（空きスペース）に参照中パスを表示！
        self.lbl_path_disp = ttk.Label(self.list_frame, text="参照中: [ - ]", font=("MS Gothic", 8, "bold"), foreground="#0284c7")
        self.lbl_path_disp.pack(fill="x", pady=(2, 1))

        list_hdr = ttk.Frame(self.list_frame)
        list_hdr.pack(fill="x", pady=2)
        ttk.Label(list_hdr, text="🎛 トラックリスト (クリックで切替)", font=("MS Gothic", 9, "bold"), foreground="#2980b9").pack(side="left")

        self.tree_tracks = ttk.Treeview(self.list_frame, show="tree", selectmode="browse")
        self.tree_tracks.pack(fill="both", expand=True, pady=2)
        self.tree_tracks.bind("<Button-1>", self.on_tree_click)

        # 右パネル: タイムラインキャンバス ＋ スクロールバー直結コントロール
        self.canvas_outer_frame = ttk.Frame(timeline_pane)
        timeline_pane.add(self.canvas_outer_frame, weight=4)

        grid_container = ttk.Frame(self.canvas_outer_frame)
        grid_container.pack(fill="both", expand=True)

        grid_container.rowconfigure(1, weight=1)
        grid_container.columnconfigure(0, weight=1)

        # 1. 時間軸上端固定ヘッダー専用キャンバス (ルーラー)
        self.header_canvas = tk.Canvas(grid_container, height=42, background="#0f172a", highlightthickness=0)
        self.header_canvas.grid(row=0, column=0, sticky="ew")

        # 2. タイムライン本体キャンバス
        self.canvas = tk.Canvas(grid_container, background="#1e293b", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")

        # 縦スクロールバー ＋ 縦ズームフェーダー
        v_bar_frame = ttk.Frame(grid_container)
        v_bar_frame.grid(row=1, column=1, sticky="ns")

        self.v_scrollbar = ttk.Scrollbar(v_bar_frame, orient="vertical", command=self.on_v_scroll)
        self.v_scrollbar.pack(fill="y", expand=True, side="top")

        v_zoom_box = ttk.Frame(v_bar_frame, padding=1)
        v_zoom_box.pack(side="bottom", fill="x", pady=2)

        ttk.Button(v_zoom_box, text="＋", width=2, command=lambda: self.adjust_zoom_y(1.2)).pack(side="top", pady=1)
        # 🌟 縦軸ズーム：最小 6.0px 〜 最大 60.0px（一画面に大量表示可能）
        self.zoom_y_slider = ttk.Scale(v_zoom_box, from_=60.0, to=6.0, value=self.zoom_y, orient="vertical", command=self.on_zoom_y_change)
        self.zoom_y_slider.pack(side="top", fill="y", expand=True, ipady=30)
        ttk.Button(v_zoom_box, text="－", width=2, command=lambda: self.adjust_zoom_y(0.8)).pack(side="bottom", pady=1)

        # 横スクロールバー ＋ 横ズームフェーダー
        h_bar_frame = ttk.Frame(grid_container)
        h_bar_frame.grid(row=2, column=0, sticky="ew")

        self.h_scrollbar = ttk.Scrollbar(h_bar_frame, orient="horizontal", command=self.on_h_scroll)
        self.h_scrollbar.pack(fill="x", expand=True, side="left")

        h_zoom_box = ttk.Frame(h_bar_frame, padding=1)
        h_zoom_box.pack(side="right", padx=2)

        ttk.Button(h_zoom_box, text="－", width=2, command=lambda: self.adjust_zoom_x(0.8)).pack(side="left", padx=1)
        # 🌟 横軸ズーム：最小 0.00005 〜 最大 0.2（何年間でも俯瞰可能、適度な拡大）
        self.zoom_x_slider = ttk.Scale(h_zoom_box, from_=0.00005, to=0.2, value=self.zoom_x, orient="horizontal", command=self.on_zoom_x_change)
        self.zoom_x_slider.pack(side="left", ipadx=30, padx=2)
        ttk.Button(h_zoom_box, text="＋", width=2, command=lambda: self.adjust_zoom_x(1.25)).pack(side="left", padx=1)

        self.canvas.configure(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        self.header_canvas.configure(xscrollcommand=self.h_scrollbar.set)

        # イベントバインド
        self.canvas.bind("<Control-MouseWheel>", self.on_ctrl_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self.on_shift_wheel)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)

    def on_h_scroll(self, *args):
        self.canvas.xview(*args)
        self.header_canvas.xview(*args)

    def redraw_legend(self):
        """🌟 実在するAIサービスのみを動的表示 ＆ クリックでカラー変更"""
        for widget in self.legend_frame.winfo_children():
            widget.destroy()

        active_services = sorted(list(set(log["service_folder"] for log in self.log_data if log.get("service_folder"))))
        if not active_services:
            active_services = ["Google AI Studio", "Gemini", "ChatGPT"]

        for s_name in active_services:
            color = self.ai_colors.get(s_name, "#3498db")
            lbl = tk.Label(
                self.legend_frame, 
                text=f" ■ {s_name} ", 
                fg=color, 
                font=("MS Gothic", 8, "bold"),
                cursor="hand2"
            )
            lbl.pack(side="left", padx=2)
            lbl.bind("<Button-1>", lambda e, name=s_name: self.change_service_color(name))

    def change_service_color(self, service_name):
        """🌟 AIサービスの色を選択変更して config.json に保存"""
        curr_color = self.ai_colors.get(service_name, "#3498db")
        new_color = colorchooser.askcolor(title=f"🎨 『{service_name}』 のテーマカラーを選択", color=curr_color)
        
        if new_color and new_color[1]:
            hex_color = new_color[1]
            self.ai_colors[service_name] = hex_color
            
            cfg = {}
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f: cfg = json.load(f)
                except: pass
            
            cfg["ai_colors"] = self.ai_colors
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
            except: pass

            self.redraw_legend()
            self.redraw_timeline()

    def on_text_pos_changed(self):
        self.text_pos_mode = self.var_text_pos.get()
        self.redraw_timeline()

    def on_group_mode_changed(self):
        """🌟 AIグループ（分ける／分けない）切り替え"""
        self.group_mode = self.var_group_mode.get()
        self.apply_sort_rule()

    def show_all_tracks(self):
        for k in self.folder_visibility: self.folder_visibility[k] = True
        for k in self.chat_visibility: self.chat_visibility[k] = True
        self.redraw_timeline()

    def hide_all_tracks(self):
        for k in self.folder_visibility: self.folder_visibility[k] = False
        for k in self.chat_visibility: self.chat_visibility[k] = False
        self.redraw_timeline()

    def on_sort_selected(self, event):
        """🌟 一括自動ソートの適用"""
        self.apply_sort_rule()

    def apply_sort_rule(self):
        """🌟 ソート基準 ＆ グループモードに応じた全チャットの一括ソート"""
        sort_mode = self.sort_var.get()

        def get_japanese_key(text):
            """あいうえお順用正規化ソートキー"""
            return unicodedata.normalize('NFKC', text).lower()

        if "開始時間が古い順" in sort_mode:
            self.log_data.sort(key=lambda x: x["start"])
        elif "開始時間が新しい順" in sort_mode:
            self.log_data.sort(key=lambda x: x["start"], reverse=True)
        elif "終了時間が古い順" in sort_mode:
            self.log_data.sort(key=lambda x: x["end"])
        elif "終了時間が新しい順" in sort_mode:
            self.log_data.sort(key=lambda x: x["end"], reverse=True)
        elif "名前順 (A-Z)" in sort_mode:
            self.log_data.sort(key=lambda x: x["name"].lower())
        elif "名前順 (Z-A)" in sort_mode:
            self.log_data.sort(key=lambda x: x["name"].lower(), reverse=True)
        elif "あいうえお順 (昇順)" in sort_mode:
            self.log_data.sort(key=lambda x: get_japanese_key(x["name"]))
        elif "あいうえお順 (降順)" in sort_mode:
            self.log_data.sort(key=lambda x: get_japanese_key(x["name"]), reverse=True)
        elif "タイムライン（期間）が長い順" in sort_mode:
            self.log_data.sort(key=lambda x: (x["end"] - x["start"]).total_seconds(), reverse=True)
        elif "タイムライン（期間）が短い順" in sort_mode:
            self.log_data.sort(key=lambda x: (x["end"] - x["start"]).total_seconds())

        self.redraw_timeline()

    def refresh_timeline_data(self):
        """🌟 動的な保存先パスから全チャットログを100%スキャン"""
        self.log_data = []
        active_dir = self.get_active_save_dir()
        self.lbl_path_disp.config(text=f"参照中: [ {active_dir} ]")

        if not os.path.exists(active_dir):
            self.redraw_legend()
            self.redraw_timeline()
            return
            
        folder_priority = ["Google AI Studio", "Gemini", "ChatGPT", "Claude", "AiReChat"]
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    folder_priority = cfg.get("folder_priority", folder_priority)
            except: pass

        all_ai_folders = [f for f in os.listdir(active_dir) if os.path.isdir(os.path.join(active_dir, f)) and f not in ["my_documents", "my_forge"]]

        def sort_key(name):
            if name in folder_priority: return (0, folder_priority.index(name))
            return (1, name)

        sorted_ai_folders = sorted(all_ai_folders, key=sort_key)

        for ai_service_folder in sorted_ai_folders:
            ai_path = os.path.join(active_dir, ai_service_folder)
            if ai_service_folder not in self.folder_visibility:
                self.folder_visibility[ai_service_folder] = True

            for chat_name in sorted(os.listdir(ai_path)):
                chat_path = os.path.join(ai_path, chat_name)
                if not os.path.isdir(chat_path): continue

                if chat_path not in self.chat_visibility:
                    self.chat_visibility[chat_path] = True

                target_md = None
                for p_key in self.source_priority:
                    if p_key == "master":
                        p_file = os.path.join(chat_path, "raw_master.md")
                        if os.path.exists(p_file):
                            target_md = p_file
                            break
                    else:
                        sp = os.path.join(chat_path, p_key)
                        if os.path.exists(sp):
                            for f in os.listdir(sp):
                                if f.endswith(".md"):
                                    target_md = os.path.join(sp, f)
                                    break
                        if target_md: break

                if not target_md or not os.path.exists(target_md):
                    target_md = os.path.join(chat_path, "summary.md")

                start_dt, end_dt, service = None, None, ai_service_folder

                if target_md and os.path.exists(target_md):
                    try:
                        with open(target_md, "r", encoding="utf-8") as f: content = f.read(3000)
                        m_s = re.search(r'true_start_time:\s*"([^"]+)"', content)
                        m_e = re.search(r'true_end_time:\s*"([^"]+)"', content)
                        m_svc = re.search(r'ai_service:\s*"([^"]+)"', content)

                        if m_svc: service = m_svc.group(1)
                        if m_s:
                            try: start_dt = datetime.datetime.strptime(m_s.group(1), "%Y-%m-%d %H:%M:%S")
                            except: pass
                        if m_e:
                            try: end_dt = datetime.datetime.strptime(m_e.group(1), "%Y-%m-%d %H:%M:%S")
                            except: pass
                    except: pass

                if not start_dt:
                    try: start_dt = datetime.datetime.fromtimestamp(os.path.getmtime(chat_path)) - datetime.timedelta(hours=1)
                    except: start_dt = datetime.datetime.now() - datetime.timedelta(hours=1)
                if not end_dt:
                    try: end_dt = datetime.datetime.fromtimestamp(os.path.getmtime(chat_path))
                    except: end_dt = datetime.datetime.now()

                self.log_data.append({
                    "id": chat_path,
                    "name": chat_name,
                    "service_folder": ai_service_folder,
                    "start": start_dt,
                    "end": end_dt,
                    "service": service
                })
            
        self.redraw_legend()
        self.apply_sort_rule()

    def redraw_timeline(self):
        """🌟 上端フリーズヘッダー ＆ 横ガイド破線 ＆ 選択ソート順 ＆ グループモード描写"""
        self.canvas.delete("all")
        self.header_canvas.delete("all")
        self.tree_tracks.delete(*self.tree_tracks.get_children())
        if not self.log_data: return

        # 🌟 「分ける」か「分けない」かのデータ並び順整理
        if self.group_mode == "split":
            # フォルダ単位でグループ化
            folder_priority = ["Google AI Studio", "Gemini", "ChatGPT", "Claude", "AiReChat"]
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        folder_priority = cfg.get("folder_priority", folder_priority)
                except: pass

            def group_sort_key(item):
                f_name = item["service_folder"]
                p_idx = folder_priority.index(f_name) if f_name in folder_priority else 999
                return (p_idx, f_name)

            # フォルダ順を重視しつつグループ化
            sorted_logs_for_render = sorted(self.log_data, key=group_sort_key)
        else:
            # 「分けない」：ソート順そのまま（フラット）
            sorted_logs_for_render = list(self.log_data)

        visible_logs = []
        for log in sorted_logs_for_render:
            f_vis = self.folder_visibility.get(log["service_folder"], True)
            c_vis = self.chat_visibility.get(log["id"], True)
            if f_vis and c_vis:
                visible_logs.append(log)

        # トラックリスト（Treeview）の構築
        if self.group_mode == "split":
            current_folder = ""
            parent_node = ""
            for log in sorted_logs_for_render:
                f_name = log["service_folder"]
                if f_name != current_folder:
                    current_folder = f_name
                    f_mark = "☑" if self.folder_visibility.get(f_name, True) else "☐"
                    parent_node = self.tree_tracks.insert("", "end", text=f"{f_mark} 📁 {f_name}", open=True, values=("folder", f_name))

                c_mark = "☑" if self.chat_visibility.get(log["id"], True) else "☐"
                self.tree_tracks.insert(parent_node, "end", text=f"{c_mark} 💬 {log['name']}", values=("chat", log["id"]))
        else:
            # 分けないモード：フラット表示
            for log in sorted_logs_for_render:
                c_mark = "☑" if self.chat_visibility.get(log["id"], True) else "☐"
                s_icon = "💬"
                self.tree_tracks.insert("", "end", text=f"{c_mark} {s_icon} [{log['service_folder']}] {log['name']}", values=("chat", log["id"]))

        if not visible_logs: return

        min_time = min(log["start"] for log in visible_logs)
        max_time = max(log["end"] for log in visible_logs)
        if min_time == max_time: max_time += datetime.timedelta(hours=1)

        if self.text_pos_mode == "left_side":
            left_margin = 210
            label_limit_x = left_margin - 8
        else:
            left_margin = 10
            label_limit_x = 0

        header_height = 42
        row_height = self.zoom_y

        total_minutes = (max_time - min_time).total_seconds() / 60
        canvas_width = left_margin + (total_minutes * self.zoom_x) + 400
        canvas_height = (len(visible_logs) * row_height) + 80

        self.canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
        self.header_canvas.configure(scrollregion=(0, 0, canvas_width, header_height))

        # 1. 時間軸上端固定ヘッダー（ルーラー）
        self.header_canvas.create_rectangle(0, 0, canvas_width, header_height, fill="#0f172a", outline="#334155")
        if self.text_pos_mode == "left_side":
            self.header_canvas.create_line(left_margin, 0, left_margin, header_height, fill="#38bdf8", width=2)
            self.canvas.create_line(left_margin, 0, left_margin, canvas_height, fill="#38bdf8", width=2)

        # 🌟 超広域〜超詳細まで対応する段階的ルーラー刻み計算
        current_marker = min_time
        last_year_month = ""

        if self.zoom_x > 0.08:
            step_delta = datetime.timedelta(hours=6)
        elif self.zoom_x > 0.02:
            step_delta = datetime.timedelta(days=1)
        elif self.zoom_x > 0.005:
            step_delta = datetime.timedelta(days=7)
        elif self.zoom_x > 0.001:
            step_delta = datetime.timedelta(days=30)
        elif self.zoom_x > 0.0002:
            step_delta = datetime.timedelta(days=90)
        else:
            step_delta = datetime.timedelta(days=365) # 数年分一括表示時

        while current_marker <= max_time + datetime.timedelta(days=30):
            minutes_from_start = (current_marker - min_time).total_seconds() / 60
            x = left_margin + (minutes_from_start * self.zoom_x)

            year_month_str = current_marker.strftime("%Y年 %m月") if self.zoom_x > 0.0005 else current_marker.strftime("%Y年")
            if year_month_str != last_year_month:
                self.header_canvas.create_text(x + 5, 11, text=year_month_str, font=("MS Gothic", 9, "bold"), fill="#38bdf8", anchor="w")
                self.header_canvas.create_line(x, 0, x, header_height, fill="#38bdf8", width=2)
                last_year_month = year_month_str

            if self.zoom_x > 0.08:
                time_label = current_marker.strftime("%d日 %H:%M")
            elif self.zoom_x > 0.02:
                time_label = current_marker.strftime("%d日")
            elif self.zoom_x > 0.005:
                time_label = current_marker.strftime("%m/%d")
            elif self.zoom_x > 0.001:
                time_label = current_marker.strftime("%Y/%m")
            else:
                time_label = current_marker.strftime("%Y")

            self.header_canvas.create_line(x, 24, x, header_height, fill="#64748b")
            self.header_canvas.create_text(x + 2, 32, text=time_label, font=("Arial", 8), fill="#94a3b8", anchor="w")

            self.canvas.create_line(x, 0, x, canvas_height, fill="#334155", dash=(2, 2))

            current_marker += step_delta

        # 2. 可視トラックの描画
        # 🌟 高さが極小の時も崩れないフォントサイズ・レイアウト調整
        font_size = 8 if row_height >= 18 else (7 if row_height >= 10 else 6)
        show_text = row_height >= 8.0

        for idx, log in enumerate(visible_logs):
            start_m = (log["start"] - min_time).total_seconds() / 60
            end_m = (log["end"] - min_time).total_seconds() / 60
            x1 = left_margin + (start_m * self.zoom_x)
            x2 = left_margin + (end_m * self.zoom_x)

            y = (idx * row_height) + 1
            h = row_height - 2
            if h < 2: h = 2
            if x2 - x1 < 2: x2 = x1 + 2

            y_mid = y + (h / 2)
            if row_height >= 10:
                self.canvas.create_line(left_margin, y_mid, canvas_width, y_mid, fill="#24324d", dash=(1, 3))

            color = "#64748b"
            service_lower = log["service_folder"].lower()
            for col_key, col_val in self.ai_colors.items():
                if col_key.lower() in service_lower or service_lower in col_key.lower():
                    color = col_val
                    break

            self.canvas.create_rectangle(x1, y, x2, y + h, fill=color, outline="#ffffff" if row_height >= 12 else color, width=1)

            clean_title = log["name"]

            if show_text:
                if self.text_pos_mode == "on_bar":
                    if x2 - x1 > 15 and row_height >= 12:
                        self.canvas.create_text(x1 + 4, y + (h/2), text=clean_title, anchor="w", font=("MS Gothic", font_size, "bold"), fill="#ffffff")
                else:
                    max_chars = 18
                    truncated_text = clean_title if len(clean_title) <= max_chars else clean_title[:max_chars-1] + "…"
                    self.canvas.create_text(label_limit_x, y + (h/2), text=truncated_text, anchor="e", font=("MS Gothic", font_size, "bold"), fill="#f8fafc")

    def on_tree_click(self, event):
        item = self.tree_tracks.identify_row(event.y)
        if not item: return

        vals = self.tree_tracks.item(item, "values")
        if not vals: return

        item_type = vals[0]
        item_id = vals[1]

        if item_type == "folder":
            curr = self.folder_visibility.get(item_id, True)
            self.folder_visibility[item_id] = not curr
        elif item_type == "chat":
            curr = self.chat_visibility.get(item_id, True)
            self.chat_visibility[item_id] = not curr

        self.redraw_timeline()

    def move_item_up(self):
        sel = self.tree_tracks.selection()
        if not sel: return
        vals = self.tree_tracks.item(sel[0], "values")
        if not vals or vals[0] != "folder": return

        target_folder = vals[1]
        folder_priority = ["Google AI Studio", "Gemini", "ChatGPT", "Claude", "AiReChat"]
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    folder_priority = cfg.get("folder_priority", folder_priority)
            except: pass

        if target_folder in folder_priority:
            idx = folder_priority.index(target_folder)
            if idx > 0:
                folder_priority[idx], folder_priority[idx - 1] = folder_priority[idx - 1], folder_priority[idx]
                self.save_folder_priority(folder_priority)

    def move_item_down(self):
        sel = self.tree_tracks.selection()
        if not sel: return
        vals = self.tree_tracks.item(sel[0], "values")
        if not vals or vals[0] != "folder": return

        target_folder = vals[1]
        folder_priority = ["Google AI Studio", "Gemini", "ChatGPT", "Claude", "AiReChat"]
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    folder_priority = cfg.get("folder_priority", folder_priority)
            except: pass

        if target_folder in folder_priority:
            idx = folder_priority.index(target_folder)
            if idx < len(folder_priority) - 1:
                folder_priority[idx], folder_priority[idx + 1] = folder_priority[idx + 1], folder_priority[idx]
                self.save_folder_priority(folder_priority)

    def save_folder_priority(self, new_priority):
        cfg = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: cfg = json.load(f)
            except: pass

        cfg["folder_priority"] = new_priority
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except: pass

        self.refresh_timeline_data()

    def on_v_scroll(self, *args):
        self.canvas.yview(*args)

    def on_zoom_x_change(self, val):
        self.zoom_x = float(val)
        self.redraw_timeline()

    def on_zoom_y_change(self, val):
        self.zoom_y = float(val)
        self.redraw_timeline()

    def adjust_zoom_x(self, factor):
        """🌟 横軸ズームの調整限界（何年分でも見渡せるよう拡張）"""
        self.zoom_x = max(0.00005, min(0.2, self.zoom_x * factor))
        self.zoom_x_slider.set(self.zoom_x)
        self.redraw_timeline()

    def adjust_zoom_y(self, factor):
        """🌟 縦軸ズームの調整限界（最小6.0pxで一括表示）"""
        self.zoom_y = max(6.0, min(60.0, self.zoom_y * factor))
        self.zoom_y_slider.set(self.zoom_y)
        self.redraw_timeline()

    def on_ctrl_wheel(self, event):
        if event.delta > 0: self.adjust_zoom_x(1.2)
        else: self.adjust_zoom_x(0.8)
        return "break"

    def on_shift_wheel(self, event):
        if event.delta > 0: self.adjust_zoom_y(1.2)
        else: self.adjust_zoom_y(0.8)
        return "break"

    def on_mouse_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"


# ================= 🖥️ 単体起動時テストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("📊 AiReAnchorTimeline - テストビジュアライザー")
    root.geometry("1200x750")

    if os.path.exists(ICON_PORTAL):
        try: root.iconbitmap(ICON_PORTAL)
        except: pass

    default_colors = {
        "Google AI Studio": "#3498db",
        "Gemini": "#2ecc71",
        "ChatGPT": "#e74c3c",
        "Claude": "#9b59b6",
        "AiReChat": "#a855f7",
        "Local LLM": "#e67e22"
    }

    timeline_frame = AiReAnchorTimelineFrame(root, None, default_colors)
    timeline_frame.pack(fill="both", expand=True, padx=10, pady=10)

    root.mainloop()