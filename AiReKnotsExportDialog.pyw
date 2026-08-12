# -*- coding: utf-8 -*-
# AiReKnotsExportDialog.pyw - カスタム物理統合マスター生成 ＆ リアルタイムプレビューダイアログ (全スペック網羅・タイムスタンプ統合対応版)
import os
import sys
import json
import re
import datetime
import shutil
import tkinter as tk
from tkinter import ttk, messagebox

# 🌟 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_KNOTS = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

# 外部モジュールの安全なインポート
try:
    from AiReKnots import AiReKnotsEngine
    HAS_KNOTS = True
except ImportError:
    HAS_KNOTS = False

# 🌟 マークダウンビューアーの安全読み込み
try:
    from AiReAnchorMarkdownViewer import render_rich_markdown
    HAS_MD_VIEWER = True
except ImportError:
    HAS_MD_VIEWER = False
    def render_rich_markdown(text_widget, content, base_dir=None, show_rich=True, show_img=True, img_refs=None, filepath=None, on_update_callback=None, progress_bar=None):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", content if content else "（データがありません）")
        text_widget.config(state="disabled")


class AiReKnotsExportDialog(tk.Toplevel):
    """🌟 カスタム物理統合マスター生成 ＆ リアルタイムプレビューダイアログ"""
    def __init__(self, parent, chat_folder_path, knots_engine=None, on_success_callback=None):
        super().__init__(parent)
        self.chat_folder_path = chat_folder_path
        self.chat_name = os.path.basename(chat_folder_path)
        self.knots_engine = knots_engine if knots_engine else (AiReKnotsEngine() if HAS_KNOTS else None)
        self.on_success_callback = on_success_callback
        
        self.title(f"⚡ 物理統合マスター・カスタム生成マネージャー: {self.chat_name}")
        self.geometry("1080x820")
        
        if os.path.exists(ICON_KNOTS):
            try: self.iconbitmap(ICON_KNOTS)
            except: pass

        self.image_refs = []
        self.scan_sources()
        self.build_ui()
        
        # 初回のプレビュー更新
        self.update_preview()

    def scan_sources(self):
        """チャット内のデータソースの存在チェック"""
        if self.knots_engine:
            self.sources = self.knots_engine.scan_chat_sources(self.chat_folder_path)
        else:
            self.sources = {}

    def _calculate_timestamps(self, time_mode):
        """🌟 選択されたルールに基づくタイムスタンプ（開始・終了日時）のリアルタイム計算"""
        times = []
        for s_key, s_info in self.sources.items():
            if s_key == "master" or not s_info.get("has_md"): continue
            raw_p = s_info.get("raw_filepath")
            if raw_p and os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8") as f: content = f.read(3000)
                    m_s = re.search(r'true_start_time:\s*"([^"]+)"', content)
                    m_e = re.search(r'true_end_time:\s*"([^"]+)"', content)
                    if m_s and m_e:
                        st_str = m_s.group(1)
                        et_str = m_e.group(1)
                        try:
                            st_dt = datetime.datetime.strptime(st_str, "%Y-%m-%d %H:%M:%S")
                            et_dt = datetime.datetime.strptime(et_str, "%Y-%m-%d %H:%M:%S")
                        except:
                            st_dt = datetime.datetime.now()
                            et_dt = st_dt
                        span = max(0, (et_dt - st_dt).total_seconds())
                        times.append({
                            "key": s_key,
                            "st_str": st_str, "et_str": et_str,
                            "st_dt": st_dt, "et_dt": et_dt,
                            "span": span
                        })
                except: pass

        if not times:
            return "不明", "不明"

        if time_mode == "timespan_source":
            # 1. 最長期間を持つ単一ソースの時間を採用
            best = max(times, key=lambda x: x["span"])
            return best["st_str"], best["et_str"]

        elif time_mode == "merge_all_time":
            # 2. 🌟 全ソースの時間を完全統合（最古開始日時 〜 最新終了日時）
            min_st = min(times, key=lambda x: x["st_dt"])["st_str"]
            max_et = max(times, key=lambda x: x["et_dt"])["et_str"]
            return min_st, max_et

        elif time_mode in ["importer_time", "scraped_time", "3rd_time"]:
            target_key = time_mode.replace("_time", "")
            for t in times:
                if t["key"] == target_key:
                    return t["st_str"], t["et_str"]
            best = max(times, key=lambda x: x["span"])
            return best["st_str"], best["et_str"]

        best = max(times, key=lambda x: x["span"])
        return best["st_str"], best["et_str"]

    def build_ui(self):
        # メイン PanedWindow
        self.main_pane = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
        self.main_pane.pack(fill="both", expand=True, padx=8, pady=6)

        # 1. 🌟 上部パラメータ設定エリア (横並び3列配置で縦スペース節約)
        param_container = ttk.Frame(self.main_pane, padding=4)
        
        param_grid_f = ttk.Frame(param_container)
        param_grid_f.pack(fill="x", expand=True)

        # --- 📌 [カテゴリ 1] 本文・会話構成の土台 ---
        c1_lf = ttk.LabelFrame(param_grid_f, text=" 📌 [1] 本文・会話構成の土台 ", padding=4)
        c1_lf.pack(side="left", fill="both", expand=True, padx=2)

        self.var_base_mode = tk.StringVar(value="timespan_first")
        
        rb1_1 = ttk.Radiobutton(c1_lf, text="⏳ 会話期間最大 [推奨]", variable=self.var_base_mode, value="timespan_first", command=self.update_preview)
        rb1_2 = ttk.Radiobutton(c1_lf, text="📊 会話容量・文字数最大", variable=self.var_base_mode, value="most_info", command=self.update_preview)
        rb1_3 = ttk.Radiobutton(c1_lf, text="📦 一括 (importer) ベース", variable=self.var_base_mode, value="importer_first", command=self.update_preview)
        rb1_4 = ttk.Radiobutton(c1_lf, text="📡 スクレイプ (scraped) ベース", variable=self.var_base_mode, value="scraped_first", command=self.update_preview)
        rb1_5 = ttk.Radiobutton(c1_lf, text="🔗 第3ソース (3rd) ベース", variable=self.var_base_mode, value="3rd_first", command=self.update_preview)

        rb1_1.pack(anchor="w", pady=1)
        rb1_2.pack(anchor="w", pady=1)
        rb1_3.pack(anchor="w", pady=1)
        rb1_4.pack(anchor="w", pady=1)
        rb1_5.pack(anchor="w", pady=1)

        # --- 🖼️ [カテゴリ 2] アセットの回収・統合範囲 ---
        c2_lf = ttk.LabelFrame(param_grid_f, text=" 🖼️ [2] アセット回収範囲 ", padding=4)
        c2_lf.pack(side="left", fill="both", expand=True, padx=2)

        self.var_asset_mode = tk.StringVar(value="all_sources")

        rb2_1 = ttk.Radiobutton(c2_lf, text="🌟 全ソースから100%回収 [推奨]", variable=self.var_asset_mode, value="all_sources", command=self.update_preview)
        rb2_2 = ttk.Radiobutton(c2_lf, text="🎯 アセット最多ソース自動選択", variable=self.var_asset_mode, value="most_assets", command=self.update_preview)
        rb2_3 = ttk.Radiobutton(c2_lf, text="📦 importer のアセットのみ", variable=self.var_asset_mode, value="importer_only", command=self.update_preview)
        rb2_4 = ttk.Radiobutton(c2_lf, text="📡 scraped のアセットのみ", variable=self.var_asset_mode, value="scraped_only", command=self.update_preview)
        rb2_5 = ttk.Radiobutton(c2_lf, text="🔗 3rd のアセットのみ", variable=self.var_asset_mode, value="3rd_only", command=self.update_preview)

        rb2_1.pack(anchor="w", pady=1)
        rb2_2.pack(anchor="w", pady=1)
        rb2_3.pack(anchor="w", pady=1)
        rb2_4.pack(anchor="w", pady=1)
        rb2_5.pack(anchor="w", pady=1)

        # --- ⏱️ [カテゴリ 3] タイムスタンプ基準 ---
        c3_lf = ttk.LabelFrame(param_grid_f, text=" ⏱️ [3] タイムスタンプ基準 ", padding=4)
        c3_lf.pack(side="left", fill="both", expand=True, padx=2)

        self.var_time_mode = tk.StringVar(value="timespan_source")

        rb3_1 = ttk.Radiobutton(c3_lf, text="⏳ 最長期間の単一ソース採用 [推奨]", variable=self.var_time_mode, value="timespan_source", command=self.update_preview)
        rb3_2 = ttk.Radiobutton(c3_lf, text="🌐 全ソースの時間を完全統合 (最古〜最新)", variable=self.var_time_mode, value="merge_all_time", command=self.update_preview)
        rb3_3 = ttk.Radiobutton(c3_lf, text="📦 importer タイムスタンプ優先", variable=self.var_time_mode, value="importer_time", command=self.update_preview)
        rb3_4 = ttk.Radiobutton(c3_lf, text="📡 scraped タイムスタンプ優先", variable=self.var_time_mode, value="scraped_time", command=self.update_preview)
        rb3_5 = ttk.Radiobutton(c3_lf, text="🔗 3rd タイムスタンプ優先", variable=self.var_time_mode, value="3rd_time", command=self.update_preview)

        rb3_1.pack(anchor="w", pady=1)
        rb3_2.pack(anchor="w", pady=1)
        rb3_3.pack(anchor="w", pady=1)
        rb3_4.pack(anchor="w", pady=1)
        rb3_5.pack(anchor="w", pady=1)

        # 存在しないソースの動的グレーアウト制御
        has_imp = self.sources.get("importer", {}).get("has_md")
        has_scr = self.sources.get("scraped", {}).get("has_md")
        has_3rd = self.sources.get("3rd", {}).get("has_md")

        if not has_imp:
            rb1_3.config(state="disabled"); rb2_3.config(state="disabled"); rb3_3.config(state="disabled")
        if not has_scr:
            rb1_4.config(state="disabled"); rb2_4.config(state="disabled"); rb3_4.config(state="disabled")
        if not has_3rd:
            rb1_5.config(state="disabled"); rb2_5.config(state="disabled"); rb3_5.config(state="disabled")

        # 🌟 予想生成スペック情報表示カード（サボらず全項目を明示！）
        spec_card = ttk.LabelFrame(param_container, text=" 📊 統合マスター確定予想スペック ", padding=6)
        spec_card.pack(fill="x", pady=(4, 0))

        self.lbl_spec_title = ttk.Label(spec_card, text=f"📌 チャット題名:  『 {self.chat_name} 』", font=("MS Gothic", 9, "bold"), foreground="#1e293b")
        self.lbl_spec_title.pack(anchor="w")

        self.lbl_spec_details = ttk.Label(
            spec_card, 
            text="⏱ 適用期間:  計算中...\n🖼 アセット総数:  - 個   |   💬 総ターン数:  - ターン   |   🔗 対象ソース:  -", 
            font=("MS Gothic", 9, "bold"), 
            foreground="#0284c7"
        )
        self.lbl_spec_details.pack(anchor="w", pady=(2, 0))

        # 2. プレビュー表示エリア
        prev_container = ttk.LabelFrame(self.main_pane, text=" 📖 カスタム統合生成プレビュー ", padding=6)
        
        ctrl_bar = ttk.Frame(prev_container)
        ctrl_bar.pack(fill="x", pady=(0, 4))

        self.rich_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_bar, text="マークダウン装飾", variable=self.rich_var, command=self.update_preview).pack(side="left", padx=4)
        
        self.img_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_bar, text="画像・動画表示", variable=self.img_var, command=self.update_preview).pack(side="left", padx=4)

        ttk.Button(ctrl_bar, text="🔍 検索 (Ctrl+F)", command=self.toggle_search_widget).pack(side="left", padx=6)

        prev_txt_f = ttk.Frame(prev_container)
        prev_txt_f.pack(fill="both", expand=True, pady=2)

        self.txt_preview = tk.Text(prev_txt_f, background="#ffffff", wrap="word")
        self.txt_preview.pack(side="left", fill="both", expand=True)

        sb_prev = ttk.Scrollbar(prev_txt_f, command=self.txt_preview.yview)
        sb_prev.pack(side="right", fill="y")
        self.txt_preview.configure(yscrollcommand=sb_prev.set)

        self.main_pane.add(param_container, minsize=170, height=190)
        self.main_pane.add(prev_container, minsize=300, height=490)

        # 3. 最下部アクションボタンエリア
        btn_box = ttk.Frame(self, padding=8)
        btn_box.pack(fill="x", side="bottom")

        self.lbl_status = ttk.Label(btn_box, text="💡 設定を変更すると即座にプレビューが更新されます。", font=("MS Gothic", 9), foreground="#2563eb")
        self.lbl_status.pack(side="left", padx=5)

        ttk.Button(btn_box, text="❌ キャンセル", command=self.destroy).pack(side="right", padx=5)
        ttk.Button(btn_box, text="⚡ このカスタム設定で物理マスターを生成", command=self.do_export_master).pack(side="right", padx=5)

    def toggle_search_widget(self):
        """VS Code風浮き島検索バーのトグル"""
        if hasattr(self.txt_preview, "floating_search_widget") and self.txt_preview.floating_search_widget.winfo_exists():
            sw = self.txt_preview.floating_search_widget
            if sw.winfo_ismapped(): sw.close_widget()
            else: sw.show_at_default_position()

    def update_preview(self):
        """🌟 パラメータ変更時のリアルタイムプレビュー ＆ 全スペック情報計算表示"""
        if not self.knots_engine: return

        # 1. タイムスタンプ範囲の計算
        start_t, end_t = self._calculate_timestamps(self.var_time_mode.get())

        # 2. 優先ルールのセット ＆ マスター構築
        old_mode = self.knots_engine.config.get("knots_priority_mode")
        self.knots_engine.config["knots_priority_mode"] = self.var_base_mode.get()

        res, err = self.knots_engine.build_integrated_master(self.chat_folder_path, is_export_master=False)

        # 設定の復元
        if old_mode: self.knots_engine.config["knots_priority_mode"] = old_mode

        if res:
            content = res["master_markdown"]

            # 🌟 マークダウン内の true_start_time / true_end_time の動的書換（計算結果の反映）
            content = re.sub(r'true_start_time:\s*"[^"]*"', f'true_start_time: "{start_t}"', content)
            content = re.sub(r'true_end_time:\s*"[^"]*"', f'true_end_time: "{end_t}"', content)
            
            # 🌟 アセットモードによるフィルタリング処理
            asset_m = self.var_asset_mode.get()
            if asset_m == "importer_only":
                content = re.sub(r'(!\s*\[.*?\]\(./(?:scraped|3rd)/assets/.*?\))', '', content)
            elif asset_m == "scraped_only":
                content = re.sub(r'(!\s*\[.*?\]\(./(?:importer|3rd)/assets/.*?\))', '', content)
            elif asset_m == "3rd_only":
                content = re.sub(r'(!\s*\[.*?\]\(./(?:importer|scraped)/assets/.*?\))', '', content)

            # アセット総数のカウント
            asset_count = len(re.findall(r'(!\s*\[.*?\]\(.*?\)|<(?:video|audio)\s+[^>]*src=)', content))
            active_srcs_str = ", ".join(res.get("sources", []))

            # 🌟 全スペックラベルの動的更新（サボらず全表記！）
            spec_str = f"⏱ 適用期間:  {start_t} 〜 {end_t}\n🖼 アセット総数:  {asset_count} 個   |   💬 総ターン数:  {res.get('total_turns', 0)} ターン   |   🔗 対象ソース:  [{active_srcs_str}]"
            self.lbl_spec_details.config(text=spec_str)

            # マークダウンビューアーの完全適用
            render_rich_markdown(
                text_widget=self.txt_preview,
                raw_text=content,
                base_dir=self.chat_folder_path,
                show_rich=self.rich_var.get(),
                show_images=self.img_var.get(),
                image_refs_list=self.image_refs
            )
            self.lbl_status.config(text=f"✅ リアルタイムプレビュー更新完了", foreground="#166534")
        else:
            self.txt_preview.config(state="normal")
            self.txt_preview.delete("1.0", tk.END)
            self.txt_preview.insert("1.0", f"⚠️ プレビュー構築エラー: {err}")
            self.txt_preview.config(state="disabled")
            self.lbl_status.config(text="❌ プレビュー更新失敗", foreground="#dc2626")

    def do_export_master(self):
        """🌟 カスタム設定での物理マスター (raw_master.md) の生成確定"""
        if not self.knots_engine: return

        # タイムスタンプ計算結果を取得して反映書き出し
        start_t, end_t = self._calculate_timestamps(self.var_time_mode.get())
        self.knots_engine.config["knots_priority_mode"] = self.var_base_mode.get()

        ok, path_or_err = self.knots_engine.export_master_cache(self.chat_folder_path)

        if ok and os.path.exists(path_or_err):
            # 物理ファイル生成後に、選ばれたタイムスタンプを物理書き込み上書き補正
            try:
                with open(path_or_err, "r", encoding="utf-8") as f:
                    final_content = f.read()
                
                final_content = re.sub(r'true_start_time:\s*"[^"]*"', f'true_start_time: "{start_t}"', final_content)
                final_content = re.sub(r'true_end_time:\s*"[^"]*"', f'true_end_time: "{end_t}"', final_content)

                # 🌟 アセットモードによるフィルタリングを再適用
                asset_m = self.var_asset_mode.get()
                if asset_m == "importer_only":
                    final_content = re.sub(r'(!\s*\[.*?\]\(./(?:scraped|3rd)/assets/.*?\))', '', final_content)
                elif asset_m == "scraped_only":
                    final_content = re.sub(r'(!\s*\[.*?\]\(./(?:importer|3rd)/assets/.*?\))', '', final_content)
                elif asset_m == "3rd_only":
                    final_content = re.sub(r'(!\s*\[.*?\]\(./(?:importer|scraped)/assets/.*?\))', '', final_content)

                with open(path_or_err, "w", encoding="utf-8") as f:
                    f.write(final_content)
            except: pass

            messagebox.showinfo("生成完了", f"『{self.chat_name}』のカスタム物理統合マスター(raw_master.md)を生成しました！")
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        else:
            messagebox.showerror("エラー", f"物理生成失敗:\n{path_or_err}")


# ================= 🖥️ 単体テストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("⚡ AiReKnotsExportDialog テストランナー")
    root.geometry("1080x820")

    test_folder = os.path.join(CURRENT_DIR, "logs", "Google AI Studio", "鎖と錨のロゴがかっこいいって話")
    
    if os.path.exists(test_folder):
        dlg = AiReKnotsExportDialog(root, test_folder)
    else:
        ttk.Label(root, text=f"テストフォルダが見つかりません:\n{test_folder}").pack(pady=50)

    root.mainloop()