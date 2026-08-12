# -*- coding: utf-8 -*-
# AiReAnchorMarkdownViewer.pyw - Webコンバーター完全準拠版 (マルチスレッドアセット解析爆速化・動的列幅テーブル搭載決定版)
import os
import re
import sys
import json
import time
import shutil
import ctypes
import winsound
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 画像処理ライブラリ Pillow (PIL) の安全読み込み
try:
    from PIL import Image, ImageTk, ImageSequence
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 動画フレーム抽出用 (OpenCV) の安全読み込み
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 完成版マルチメディアエンジン AiReMediaPlayer.pyw の安全読み込み
try:
    from AiReMediaPlayer import InlineAudioPlayerCard, InlineVideoPlayerCard, InlineImageGifPlayerCard
    HAS_AIRE_MEDIA_PLAYER = True
except ImportError:
    HAS_AIRE_MEDIA_PLAYER = False

# Windows AppID 登録
try:
    myappid = 'airelinker.suite.viewer.v19'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
PROJECT_DIR = CURRENT_DIR
ICON_PORTAL = os.path.normpath(os.path.join(PROJECT_DIR, "icon", "AiReAnchor.ico"))


# ================= 🛠 パス解決 ＆ エスケープヘルパー =================
def calc_display_width(text):
    """🌟 全角文字（2文字分）と半角文字（1文字分）を判別して正確な表示長を計算"""
    if not text: return 0
    w = 0
    for ch in str(text):
        if ord(ch) > 255:
            w += 2
        else:
            w += 1
    return w


def get_dismissed_json_path(base_dir):
    if not base_dir: return os.path.join(PROJECT_DIR, "dismissed_candidates.json")
    norm_base = os.path.normpath(base_dir)
    if os.path.basename(norm_base).lower() == "scraped":
        return os.path.join(norm_base, "dismissed_candidates.json")
    return os.path.join(norm_base, "scraped", "dismissed_candidates.json")


def open_assets_folder_in_explorer(base_dir):
    if not base_dir or not os.path.exists(base_dir):
        messagebox.showwarning("警告", "アセットフォルダの参照先が見つかりません。")
        return

    possible_assets_dirs = [
        os.path.join(base_dir, "assets"),
        os.path.join(base_dir, "scraped", "assets"),
        os.path.join(base_dir, "importer", "assets"),
        os.path.join(base_dir, "3rd", "assets"),
        base_dir
    ]

    target_dir = None
    for d in possible_assets_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            target_dir = d
            break

    if target_dir:
        try: os.startfile(target_dir)
        except Exception as e: messagebox.showerror("エラー", f"フォルダを開けませんでした:\n{e}")
    else:
        messagebox.showwarning("フォルダなし", "アセットフォルダ(assets/)が存在しません。")


def setup_widget_ux_helpers(widget, target_text_widget, cursor_type="arrow"):
    try: widget.config(cursor=cursor_type)
    except: pass

    def on_mouse_wheel(event):
        try: target_text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except: pass
        return "break"

    def bind_recursive(w):
        try:
            w.bind("<MouseWheel>", on_mouse_wheel)
            for child in w.winfo_children():
                bind_recursive(child)
        except: pass

    bind_recursive(widget)


def calculate_similarity(str1, str2):
    if not str1 or not str2: return 0.0
    set1, set2 = set(str1.lower()), set(str2.lower())
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


def get_visible_scroll_state(text_widget):
    try:
        y_ratio = text_widget.yview()[0]
        top_idx = text_widget.index("@0,0")
        line_num = int(top_idx.split(".")[0])
        
        dinfo = text_widget.dlineinfo(top_idx)
        y_offset = dinfo[1] if dinfo else 0

        raw_anchor_text = ""
        for offset in range(10):
            check_line = line_num + offset
            t = text_widget.get(f"{check_line}.0", f"{check_line}.end").strip()
            if t and not t.startswith("□") and not t.startswith("■") and not t.startswith("#") and len(t) >= 4:
                raw_anchor_text = t[:25]
                break

        return y_ratio, line_num, raw_anchor_text, y_offset
    except:
        return 0.0, 1, "", 0


def restore_visible_scroll_state(text_widget, state):
    try:
        y_ratio, line_num, raw_anchor_text, orig_y_offset = state
        text_widget.update_idletasks()

        restored_idx = None
        if raw_anchor_text and len(raw_anchor_text) >= 3:
            found = text_widget.search(raw_anchor_text, "1.0", stopindex=tk.END)
            if found: restored_idx = found

        if not restored_idx:
            total_lines = int(text_widget.index("end-1c").split(".")[0])
            target_line = min(line_num, total_lines)
            restored_idx = f"{target_line}.0"

        text_widget.see(restored_idx)
        text_widget.update_idletasks()

        new_dinfo = text_widget.dlineinfo(restored_idx)
        if new_dinfo:
            current_y = new_dinfo[1]
            diff_y = current_y - orig_y_offset
            if abs(diff_y) > 1:
                text_widget.yview_scroll(int(diff_y), "pixels")
                text_widget.update_idletasks()

        curr_y = text_widget.yview()[0]
        if y_ratio > 0.02 and curr_y < 0.01:
            text_widget.yview_moveto(y_ratio)
            text_widget.update_idletasks()
    except:
        try:
            text_widget.yview_moveto(state[0])
            text_widget.update_idletasks()
        except: pass


def _worker_calc_asset_sim(args):
    """🌟 マルチスレッド用 1アセット候補ファイルの類似度計算ワーカー"""
    f_path, f, base_name, target_ext = args
    audio_exts = ["mp3", "wav", "ogg", "m4a", "flac", "aac", "wma"]
    video_exts = ["mp4", "webm", "avi", "mov", "wmv", "mkv", "flv"]
    image_exts = ["png", "jpg", "jpeg", "gif", "ico", "webp", "bmp"]

    def is_same_category(ext1, ext2):
        if ext1 in audio_exts and ext2 in audio_exts: return True
        if ext1 in video_exts and ext2 in video_exts: return True
        if ext1 in image_exts and ext2 in image_exts: return True
        return False

    try:
        if f.endswith(".bin"): return None
        f_ext = f.split(".")[-1].lower() if "." in f else ""
        if target_ext and not is_same_category(target_ext, f_ext):
            return None

        sim = calculate_similarity(base_name, f.split(".")[0])
        if sim >= 0.60:
            return sim, f, f_path
    except: pass
    return None


def find_candidate_lost_asset(missing_rel_path, base_dir):
    """🌟 マルチスレッド並列処理（ThreadPoolExecutor）による迷子アセット候補の爆速検索"""
    fname = os.path.basename(missing_rel_path)
    base_name, target_ext = os.path.splitext(fname)
    target_ext = target_ext.lower().replace(".", "")

    search_dirs = [
        os.path.normpath(os.path.join(PROJECT_DIR, "logs", "candidate_assets")),
        os.path.join(base_dir, "candidate_assets"),
        os.path.join(os.path.dirname(base_dir), "candidate_assets"),
        os.path.join(base_dir, "test_assets"),
        os.path.join(base_dir, "incoming_assets"),
        base_dir
    ]

    candidate_tasks = []
    for s_dir in search_dirs:
        if os.path.exists(s_dir) and os.path.isdir(s_dir):
            for f in os.listdir(s_dir):
                f_path = os.path.join(s_dir, f)
                if os.path.isfile(f_path):
                    candidate_tasks.append((f_path, f, base_name, target_ext))

    if not candidate_tasks:
        return None, None

    best_match_file = None
    best_match_path = None
    highest_sim = 0.0

    # 🌟 CPUマルチスレッドで一斉並列計算
    max_workers = min(32, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker_calc_asset_sim, task) for task in candidate_tasks]
        for future in as_completed(futures):
            res = future.result()
            if res:
                sim, f, f_path = res
                if sim > highest_sim:
                    highest_sim = sim
                    best_match_file = f
                    best_match_path = f_path

    return best_match_file, best_match_path


def update_markdown_asset_path(raw_filepath, old_ref, new_tag):
    if not raw_filepath or not os.path.exists(raw_filepath): return False
    try:
        with open(raw_filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        if old_ref in content:
            updated_content = content.replace(old_ref, new_tag)
        else:
            fname = os.path.basename(old_ref)
            escaped_fn = re.escape(fname)
            
            pattern_vid = r'<(?:video|audio)\s+[^>]*src=["\'][^"\']*' + escaped_fn + r'["\'][^>]*>(?:</(?:video|audio)>)?'
            if re.search(pattern_vid, content, re.IGNORECASE):
                updated_content = re.sub(pattern_vid, new_tag, content, flags=re.IGNORECASE)
            elif re.search(r'!\[.*?\]\([^)]*' + escaped_fn + r'\)', content):
                updated_content = re.sub(r'!\[.*?\]\([^)]*' + escaped_fn + r'\)', new_tag, content)
            elif re.search(r'\[📎\s*添付ファイル:[^\]]+\]\([^)]*' + escaped_fn + r'\)', content):
                updated_content = re.sub(r'\[📎\s*添付ファイル:[^\]]+\]\([^)]*' + escaped_fn + r'\)', new_tag, content)
            elif fname in content:
                updated_content = content.replace(fname, new_tag)
            else:
                return False

        with open(raw_filepath, "w", encoding="utf-8") as f:
            f.write(updated_content)
        return True
    except Exception as e:
        print("update asset path error:", e)
        return False


def unlink_markdown_asset_tag(raw_filepath, target_ref):
    if not raw_filepath or not os.path.exists(raw_filepath): return False
    try:
        with open(raw_filepath, "r", encoding="utf-8") as f: content = f.read()
        fname = os.path.basename(target_ref)
        content = re.sub(r'<(?:video|audio)\s+[^>]*src=["\']' + re.escape(target_ref) + r'["\'][^>]*>(?:</(?:video|audio)>)?', fname, content, flags=re.IGNORECASE)
        content = re.sub(r'!\[.*?\]\(' + re.escape(target_ref) + r'\)', fname, content)
        content = re.sub(r'\[📎\s*添付ファイル:[^\]]+\]\(' + re.escape(target_ref) + r'\)', fname, content)
        if target_ref in content: content = content.replace(target_ref, fname)
        with open(raw_filepath, "w", encoding="utf-8") as f: f.write(content)
        return True
    except: return False


# ================= 🎨 VS Code 風 ドラッグ移動対応 画面内フローティング検索バー =================
class VSCodeFloatingSearchWidget(tk.Frame):
    def __init__(self, parent_container, text_widget):
        super().__init__(parent_container, bg="#1e293b", bd=1, relief="solid", padx=6, pady=4)
        self.parent_container = parent_container
        self.text_widget = text_widget
        
        self.matches = []
        self.current_match_idx = -1

        self._drag_x = 0
        self._drag_y = 0

        self.build_ui()
        self.bind_drag_events()

    def build_ui(self):
        lbl_drag = tk.Label(self, text="⋮⋮", bg="#1e293b", fg="#94a3b8", cursor="fleur", font=("MS Gothic", 9, "bold"))
        lbl_drag.pack(side="left", padx=(0, 4))
        lbl_drag.bind("<Button-1>", self.start_drag)
        lbl_drag.bind("<B1-Motion>", self.do_drag)

        self.entry_q = tk.Entry(self, bg="#0f172a", fg="#f8fafc", insertbackground="white", bd=1, relief="flat", width=18, font=("MS Gothic", 9))
        self.entry_q.pack(side="left", padx=2, ipady=2)

        self.lbl_count = tk.Label(self, text="結果なし", bg="#1e293b", fg="#94a3b8", font=("MS Gothic", 8))
        self.lbl_count.pack(side="left", padx=6)

        btn_prev = tk.Button(self, text="↑", bg="#334155", fg="white", activebackground="#475569", activeforeground="white", bd=0, width=2, font=("MS Gothic", 8, "bold"), command=self.search_prev)
        btn_prev.pack(side="left", padx=1)

        btn_next = tk.Button(self, text="↓", bg="#334155", fg="white", activebackground="#475569", activeforeground="white", bd=0, width=2, font=("MS Gothic", 8, "bold"), command=self.search_next)
        btn_next.pack(side="left", padx=1)

        btn_close = tk.Button(self, text="✕", bg="#1e293b", fg="#94a3b8", activebackground="#dc2626", activeforeground="white", bd=0, width=2, font=("MS Gothic", 8, "bold"), command=self.close_widget)
        btn_close.pack(side="left", padx=(4, 0))

        self.entry_q.bind("<KeyRelease>", lambda e: self.perform_search_all())
        self.entry_q.bind("<Return>", lambda e: self.search_next())
        self.entry_q.bind("<Shift-Return>", lambda e: self.search_prev())
        self.entry_q.bind("<Escape>", lambda e: self.close_widget())

    def bind_drag_events(self):
        self.bind("<Button-1>", self.start_drag)
        self.bind("<B1-Motion>", self.do_drag)

    def start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def do_drag(self, event):
        x = self.winfo_x() + (event.x - self._drag_x)
        y = self.winfo_y() + (event.y - self._drag_y)
        self.place(x=x, y=y, relx=0, rely=0, anchor="nw")

    def show_at_default_position(self):
        self.place(relx=1.0, rely=0.0, x=-15, y=10, anchor="ne")
        self.lift()
        self.entry_q.focus_set()

    def close_widget(self):
        self.clear_highlight()
        self.place_forget()

    def clear_highlight(self):
        self.text_widget.tag_remove("search_highlight", "1.0", tk.END)
        self.text_widget.tag_remove("search_current", "1.0", tk.END)
        self.matches.clear()
        self.current_match_idx = -1
        self.lbl_count.config(text="結果なし")

    def perform_search_all(self):
        query = self.entry_q.get().strip()
        self.clear_highlight()
        if not query: return

        self.text_widget.tag_config("search_highlight", background="#fde047", foreground="#000000")
        self.text_widget.tag_config("search_current", background="#f97316", foreground="#ffffff")

        idx = "1.0"
        while True:
            idx = self.text_widget.search(query, idx, stopindex=tk.END, nocase=True)
            if not idx: break
            end_idx = f"{idx}+{len(query)}c"
            self.matches.append((idx, end_idx))
            self.text_widget.tag_add("search_highlight", idx, end_idx)
            idx = end_idx

        total = len(self.matches)
        if total > 0:
            self.current_match_idx = 0
            self.highlight_current()
        else:
            self.lbl_count.config(text="結果なし")

    def highlight_current(self):
        if not self.matches or self.current_match_idx < 0: return
        self.text_widget.tag_remove("search_current", "1.0", tk.END)
        
        idx, end_idx = self.matches[self.current_match_idx]
        self.text_widget.tag_add("search_current", idx, end_idx)
        self.text_widget.see(idx)
        
        total = len(self.matches)
        self.lbl_count.config(text=f"{self.current_match_idx + 1}/{total}件")

    def search_next(self):
        if not self.matches:
            self.perform_search_all()
            return
        self.current_match_idx = (self.current_match_idx + 1) % len(self.matches)
        self.highlight_current()

    def search_prev(self):
        if not self.matches:
            self.perform_search_all()
            return
        self.current_match_idx = (self.current_match_idx - 1) % len(self.matches)
        self.highlight_current()


# ================= 🌟 枠線テーブル ＆ インデント対応Web準拠レンダラー =================
def render_rich_markdown(text_widget, raw_text, base_dir, show_rich=True, show_images=True, image_refs_list=None, filepath=None, on_update_callback=None, progress_bar=None, show_style="simple_md"):
    if show_style == "simple": show_style = "simple_md"
    elif show_style == "aire": show_style = "simple_aire"
    elif show_style == "rich": show_style = "rich_md"
    elif show_style == "raw": show_style = "none"

    if not show_rich:
        show_style = "none"

    if progress_bar:
        try:
            progress_bar.pack(side="left", padx=5)
            progress_bar.start(10)
        except: pass

    try:
        parent_container = text_widget.master
        if not hasattr(text_widget, "floating_search_widget") or not text_widget.floating_search_widget.winfo_exists():
            search_widget = VSCodeFloatingSearchWidget(parent_container, text_widget)
            text_widget.floating_search_widget = search_widget

            def on_ctrl_f_event(e):
                if search_widget.winfo_ismapped():
                    search_widget.close_widget()
                else:
                    search_widget.show_at_default_position()
                return "break"

            text_widget.bind("<Control-f>", on_ctrl_f_event)
            text_widget.bind("<Control-F>", on_ctrl_f_event)
    except: pass

    if not filepath and base_dir:
        for possible_name in ["raw_scraped.md", "raw_master.md", "raw_test.md", "raw_incoming.md", "raw_3rd.md"]:
            cand_p = os.path.join(base_dir, possible_name)
            if os.path.exists(cand_p):
                filepath = cand_p
                break
            cand_p_scraped = os.path.join(base_dir, "scraped", possible_name)
            if os.path.exists(cand_p_scraped):
                filepath = cand_p_scraped
                break

    scroll_state = get_visible_scroll_state(text_widget)

    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    
    # スタイル設定
    text_widget.tag_config("h1", font=("MS Gothic", 16, "bold"), foreground="#2c3e50", spacing1=10, spacing2=5)
    text_widget.tag_config("h2", font=("MS Gothic", 13, "bold"), foreground="#2980b9", spacing1=8, spacing2=4)
    text_widget.tag_config("h3", font=("MS Gothic", 11, "bold"), foreground="#27ae60", spacing1=6, spacing2=3)
    text_widget.tag_config("bold", font=("MS Gothic", 9, "bold"))
    text_widget.tag_config("quote", font=("MS Gothic", 9, "italic"), foreground="#7f8c8d", background="#f8f9fa", lmargin1=20, lmargin2=20)
    text_widget.tag_config("user_header", font=("MS Gothic", 10, "bold"), foreground="#2980b9", spacing1=15)
    text_widget.tag_config("model_header", font=("MS Gothic", 10, "bold"), foreground="#27ae60", spacing1=15)

    # リッチスタイル (ChatGPT / Gemini 風)
    text_widget.tag_config("rich_h1", font=("MS Gothic", 20, "bold"), foreground="#0f172a", background="#e2e8f0", spacing1=18, spacing2=8, lmargin1=10, lmargin2=10)
    text_widget.tag_config("rich_h2", font=("MS Gothic", 15, "bold"), foreground="#0284c7", spacing1=14, spacing2=6, lmargin1=8)
    text_widget.tag_config("rich_h3", font=("MS Gothic", 12, "bold"), foreground="#0d9488", spacing1=10, spacing2=4, lmargin1=6)
    text_widget.tag_config("rich_quote", font=("MS Gothic", 10), foreground="#1e293b", background="#e0f2fe", lmargin1=24, lmargin2=24, rmargin=24, spacing1=6, spacing3=6)
    text_widget.tag_config("rich_list_num", font=("MS Gothic", 10, "bold"), foreground="#0284c7", lmargin1=16, lmargin2=32)
    text_widget.tag_config("rich_list_bullet", font=("MS Gothic", 10, "bold"), foreground="#0d9488", lmargin1=16, lmargin2=32)
    text_widget.tag_config("rich_code_block", font=("Consolas", 10), foreground="#f8fafc", background="#1e293b", lmargin1=16, lmargin2=16, rmargin=16)

    if image_refs_list is not None:
        image_refs_list.clear()
    else:
        image_refs_list = []

    if show_style == "none":
        text_widget.insert(tk.END, raw_text)
        text_widget.config(state="disabled")
        text_widget.update_idletasks()
        restore_visible_scroll_state(text_widget, scroll_state)
        if progress_bar:
            try:
                progress_bar.stop()
                progress_bar.pack_forget()
            except: pass
        return

    lines = raw_text.split("\n")
    
    yaml_bounds = []
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            yaml_bounds.append(idx)
            if len(yaml_bounds) == 2: break
                
    start_line_idx = 0
    if len(yaml_bounds) == 2:
        start_line_idx = yaml_bounds[1] + 1

    def handle_unlink_asset(ref_str):
        if messagebox.askyesno("解除確認", f"文章本文・メディア名は保持したまま、アセットリンクを解除しますか？\n({os.path.basename(ref_str)})"):
            if unlink_markdown_asset_tag(filepath, ref_str):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        new_content = f.read()
                    render_rich_markdown(text_widget, new_content, base_dir, show_rich, show_images, image_refs_list, filepath, on_update_callback, progress_bar, show_style)
                except:
                    if on_update_callback: on_update_callback()

    def handle_replace_asset_with_dialog(old_ref_str, pre_selected_cand_path=None):
        logs_candidate_dir = os.path.normpath(os.path.join(PROJECT_DIR, "logs", "candidate_assets"))
        
        if pre_selected_cand_path and os.path.exists(pre_selected_cand_path):
            initial_search_dir = os.path.dirname(pre_selected_cand_path)
            initial_file = os.path.basename(pre_selected_cand_path)
        else:
            initial_search_dir = logs_candidate_dir if os.path.exists(logs_candidate_dir) else os.path.join(base_dir, "candidate_assets")
            if not os.path.exists(initial_search_dir): initial_search_dir = base_dir
            initial_file = ""

        new_file = filedialog.askopenfilename(
            title="🔍 アセットファイルを選択（そのまま開けば候補を確定適用）",
            initialdir=initial_search_dir,
            initialfile=initial_file,
            filetypes=[("All Files", "*.*")]
        )

        if new_file and os.path.exists(new_file):
            new_fname = os.path.basename(new_file)
            target_assets_dir = os.path.join(base_dir, "assets")
            os.makedirs(target_assets_dir, exist_ok=True)
            dst_path = os.path.join(target_assets_dir, new_fname)
            shutil.copy2(new_file, dst_path)
            
            ext_l = new_fname.split(".")[-1].lower() if "." in new_fname else ""
            if ext_l in ["mp4", "webm", "mov", "avi", "wmv", "mkv"]:
                new_tag = f'<video src="./assets/{new_fname}" controls width="420"></video>'
            elif ext_l in ["mp3", "wav", "ogg", "m4a", "flac", "aac", "wma"]:
                new_tag = f'<audio src="./assets/{new_fname}" controls></audio>'
            elif ext_l in ["xlsx", "xls", "csv", "pdf", "zip"]:
                new_tag = f'[📎 添付ファイル: {new_fname}](./assets/{new_fname})'
            else:
                new_tag = f'![添付メディア](./assets/{new_fname})'

            if update_markdown_asset_path(filepath, old_ref_str, new_tag):
                messagebox.showinfo("確定適用成功", f"アセット 『{new_fname}』 を正式アセットフォルダに格納し適用しました！")
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        new_content = f.read()
                    render_rich_markdown(text_widget, new_content, base_dir, show_rich, show_images, image_refs_list, filepath, on_update_callback, progress_bar, show_style)
                except:
                    if on_update_callback: on_update_callback()

    def handle_dismiss_candidate(plain_fname):
        if messagebox.askyesno("提案削除確認", f"この候補提案を非表示削除しますか？\n（今後この箇所に同じ提案は表示されなくなります）"):
            try:
                dismiss_file = get_dismissed_json_path(base_dir)
                os.makedirs(os.path.dirname(dismiss_file), exist_ok=True)
                
                dismissed = {}
                if os.path.exists(dismiss_file):
                    try:
                        with open(dismiss_file, "r", encoding="utf-8") as df:
                            dismissed = json.load(df)
                    except: pass
                
                dismissed[plain_fname] = True
                with open(dismiss_file, "w", encoding="utf-8") as df:
                    json.dump(dismissed, df, indent=4, ensure_ascii=False)
                
                if on_update_callback: on_update_callback()
            except Exception as e:
                messagebox.showerror("エラー", f"提案の削除に失敗しました: {e}")

    def is_candidate_dismissed(plain_fname):
        dismiss_file = get_dismissed_json_path(base_dir)
        if os.path.exists(dismiss_file):
            try:
                with open(dismiss_file, "r", encoding="utf-8") as df:
                    dismissed = json.load(df)
                    return dismissed.get(plain_fname, False)
            except: pass
        return False

    def open_external_app(target_path):
        if os.path.exists(target_path):
            try: os.startfile(target_path)
            except Exception as e: messagebox.showerror("再生エラー", f"ファイルを開けませんでした:\n{e}")
        else:
            messagebox.showwarning("ファイルなし", f"指定ファイルが存在しません:\n{target_path}")

    hide_thinking = (show_style in ["simple_aire", "rich_aire"])
    is_rich_mode = (show_style in ["rich_md", "rich_aire"])

    in_model_block = False
    in_thinking_process = False
    in_code_block = False
    
    # 🌟 テーブルのブロック解析用バッファ
    table_lines_buffer = []

    def flush_table_buffer():
        """🌟 動的列幅自動拡大 ＆ 横スクロールバー付きレスポンシブ・本物枠線テーブル埋め込み描画"""
        if not table_lines_buffer: return

        try:
            parsed_rows = []
            for t_line in table_lines_buffer:
                cells = [c.strip() for c in t_line.strip().strip("|").split("|")]
                # 区切り行 ( | :--- | :--- | ) はスキップ
                if all(re.match(r'^:?-+:?$', c) for c in cells if c):
                    continue
                if any(cells):
                    parsed_rows.append(cells)

            if len(parsed_rows) >= 1:
                header = parsed_rows[0]
                data_rows = parsed_rows[1:]

                # 綺麗な表フレームの生成
                tbl_frame = tk.Frame(text_widget, bg="#cbd5e1", bd=1, relief="solid")
                setup_widget_ux_helpers(tbl_frame, text_widget)

                cols = [f"col_{i}" for i in range(len(header))]
                tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", height=min(14, max(2, len(data_rows))))
                
                # 🌟 各列の表示長（文字数）を分析し列幅を自動フィット（動的計算）
                for idx, col_id in enumerate(cols):
                    col_title = header[idx] if idx < len(header) else ""
                    max_w = calc_display_width(col_title)
                    for row in data_rows:
                        if idx < len(row):
                            max_w = max(max_w, calc_display_width(row[idx]))
                    
                    # セルテキストの長さに応じてピクセル幅を拡張（最小120px、最大750px）
                    col_pixel_width = max(120, min(750, int(max_w * 8.5 + 28)))
                    tree.heading(col_id, text=col_title)
                    tree.column(col_id, width=col_pixel_width, minwidth=80, anchor="w")

                for row in data_rows:
                    tree.insert("", "end", values=row)

                # 🌟 水平（横）スクロールバー ＆ 垂直（縦）スクロールバーの完全配備
                x_sb = ttk.Scrollbar(tbl_frame, orient="horizontal", command=tree.xview)
                y_sb = ttk.Scrollbar(tbl_frame, orient="vertical", command=tree.yview)
                tree.configure(xscrollcommand=x_sb.set, yscrollcommand=y_sb.set)

                tree.grid(row=0, column=0, sticky="nsew")
                y_sb.grid(row=0, column=1, sticky="ns")
                x_sb.grid(row=1, column=0, sticky="ew")

                tbl_frame.grid_rowconfigure(0, weight=1)
                tbl_frame.grid_columnconfigure(0, weight=1)

                setup_widget_ux_helpers(tree, text_widget)

                text_widget.window_create(tk.END, window=tbl_frame)
                text_widget.insert(tk.END, "\n\n")
        except:
            for raw_l in table_lines_buffer:
                text_widget.insert(tk.END, raw_l + "\n")
        
        table_lines_buffer.clear()

    # 本文解析ループ
    for idx_line, line in enumerate(lines[start_line_idx:]):
        trimmed_line = line.strip()

        # 🌟 テーブル行 (| ... |) の連続検出とバッファリング
        if trimmed_line.startswith("|") and trimmed_line.endswith("|") and len(trimmed_line) > 2:
            table_lines_buffer.append(trimmed_line)
            continue
        else:
            if table_lines_buffer:
                flush_table_buffer()

        # コードブロック (```) の判定
        if trimmed_line.startswith("```"):
            in_code_block = not in_code_block
            if is_rich_mode:
                if in_code_block:
                    text_widget.insert(tk.END, "💻 【コード・プログラムブロック】\n", "rich_code_block")
                else:
                    text_widget.insert(tk.END, "\n", "rich_code_block")
                continue

        if in_code_block and is_rich_mode:
            text_widget.insert(tk.END, line + "\n", "rich_code_block")
            continue

        # 発言ヘッダーの検出
        if trimmed_line.startswith("### 👤") or trimmed_line.startswith("### [USER]") or trimmed_line.startswith("□ ユーザー") or trimmed_line.startswith("### USER"):
            in_model_block = False
            in_thinking_process = False
            hdr_txt = "\n👤 USERの発言\n" if is_rich_mode else "\n□ ユーザーの発言\n"
            text_widget.insert(tk.END, hdr_txt, "user_header")
            continue
        elif trimmed_line.startswith("### 🤖") or trimmed_line.startswith("### [MODEL]") or trimmed_line.startswith("■ AI") or trimmed_line.startswith("### MODEL"):
            in_model_block = True
            in_thinking_process = False
            hdr_txt = "\n🤖 MODELの応答\n" if is_rich_mode else "\n■ AIモデルの応答\n"
            text_widget.insert(tk.END, hdr_txt, "model_header")
            continue

        # 英語思考プロセス (Thoughts) の判定
        if in_model_block:
            if re.match(r'^\*\*[A-Za-z0-9\s—–\-,\.:;]+\*\*\s*$', trimmed_line):
                in_thinking_process = True
            if re.search(r'[\u3040-\u30FF\u4E00-\u9FFF]', line) or line.startswith("#") or line.startswith("|") or line.startswith("---"):
                in_thinking_process = False

            if hide_thinking and in_thinking_process:
                continue

        # 水平線 (--- や ***) の本物ライン描画
        if trimmed_line in ["---", "***", "___"]:
            if is_rich_mode:
                div_frame = tk.Frame(text_widget, height=2, bg="#0284c7", bd=0)
                setup_widget_ux_helpers(div_frame, text_widget)
                text_widget.window_create(tk.END, window=div_frame)
                text_widget.insert(tk.END, "\n\n")
            else:
                text_widget.insert(tk.END, "---\n")
            continue

        # 見出しの描画
        if line.startswith("# "):
            tag = "rich_h1" if is_rich_mode else "h1"
            prefix = "📌 " if is_rich_mode else ""
            text_widget.insert(tk.END, prefix + line[2:] + "\n", tag)
            continue
        elif line.startswith("## "):
            tag = "rich_h2" if is_rich_mode else "h2"
            prefix = "📜 " if is_rich_mode else ""
            text_widget.insert(tk.END, prefix + line[3:] + "\n", tag)
            continue
        elif line.startswith("### "):
            tag = "rich_h3" if is_rich_mode else "h3"
            prefix = "💡 " if is_rich_mode else ""
            text_widget.insert(tk.END, prefix + line[4:] + "\n", tag)
            continue
        elif line.startswith("> "):
            tag = "rich_quote" if is_rich_mode else "quote"
            prefix = "💬 " if is_rich_mode else ""
            text_widget.insert(tk.END, prefix + line[2:] + "\n", tag)
            continue

        # 🌟 リスト (1., 2., *, -) の段落インデント ＆ 部分太字レンダリング
        num_match = re.match(r'^\s*(\d+\.)\s+(.*)', line)
        bullet_match = re.match(r'^\s*(\*|-)\s+(.*)', line)

        if is_rich_mode and (num_match or bullet_match):
            if num_match:
                prefix_str = f"  {num_match.group(1)} "
                body_str = num_match.group(2)
                text_widget.insert(tk.END, prefix_str, "rich_list_num")
            else:
                prefix_str = "  • "
                body_str = bullet_match.group(2)
                text_widget.insert(tk.END, prefix_str, "rich_list_bullet")

            # 行内の部分太字 (**...**) の適用
            if "**" in body_str:
                parts = body_str.split("**")
                for idx, part in enumerate(parts):
                    if idx % 2 == 1: text_widget.insert(tk.END, part, "bold")
                    else: text_widget.insert(tk.END, part)
            else:
                text_widget.insert(tk.END, body_str)
            text_widget.insert(tk.END, "\n")
            continue

        # 動画・音声・画像・ドキュメント埋め込みタグ処理
        vid_match = re.search(r'<video\s+[^>]*src=["\'](.*?)["\'][^>]*>', line, re.IGNORECASE)
        if vid_match:
            rel_path = vid_match.group(1)
            vid_path = os.path.normpath(os.path.join(base_dir, rel_path))
            fname = os.path.basename(vid_path)

            if show_images and HAS_AIRE_MEDIA_PLAYER:
                v_card = InlineVideoPlayerCard(text_widget, vid_path, fname, rel_path, filepath, base_dir, on_update_callback, text_widget)
                setup_widget_ux_helpers(v_card, text_widget)
                text_widget.window_create(tk.END, window=v_card)
                text_widget.insert(tk.END, "\n\n")
                continue

        aud_match = re.search(r'<audio\s+[^>]*src=["\'](.*?)["\'][^>]*>', line, re.IGNORECASE)
        aud_file_match = re.search(r'[\w\-\.\%\s\u3000-\u30ff\u4e00-\u9fff]+\.(?:mp3|wav|ogg|m4a|flac|aac|wma)\b', line, re.IGNORECASE)

        if aud_match or (aud_file_match and not re.search(r'!\[.*?\]', line)):
            rel_path = aud_match.group(1) if aud_match else f"./assets/{aud_file_match.group(0)}"
            aud_path = os.path.normpath(os.path.join(base_dir, rel_path))
            fname = os.path.basename(aud_path)

            if show_images and os.path.exists(aud_path) and HAS_AIRE_MEDIA_PLAYER:
                a_card = InlineAudioPlayerCard(text_widget, aud_path, fname, rel_path, filepath, base_dir, on_update_callback, text_widget)
                setup_widget_ux_helpers(a_card, text_widget)
                text_widget.window_create(tk.END, window=a_card)
                text_widget.insert(tk.END, "\n\n")
                continue

        img_match = re.search(r"!\[.*?\]\((.*?)\)", line)
        if img_match:
            rel_path = img_match.group(1)
            img_path = os.path.normpath(os.path.join(base_dir, rel_path))
            fname = os.path.basename(img_path)

            ext_check = fname.split(".")[-1].lower() if "." in fname else ""
            if ext_check in ["mp3", "wav", "ogg", "m4a", "flac"] and os.path.exists(img_path) and HAS_AIRE_MEDIA_PLAYER and show_images:
                a_card = InlineAudioPlayerCard(text_widget, img_path, fname, rel_path, filepath, base_dir, on_update_callback, text_widget)
                setup_widget_ux_helpers(a_card, text_widget)
                text_widget.window_create(tk.END, window=a_card)
                text_widget.insert(tk.END, "\n\n")
                continue

            if show_images:
                if os.path.exists(img_path):
                    try:
                        if ext_check in ["gif", "ico"] and HAS_AIRE_MEDIA_PLAYER:
                            gif_card = InlineImageGifPlayerCard(text_widget, img_path, fname, rel_path, filepath, base_dir)
                            setup_widget_ux_helpers(gif_card, text_widget)
                            text_widget.window_create(tk.END, window=gif_card)
                            text_widget.insert(tk.END, "\n\n")
                            continue

                        if HAS_PIL:
                            img = Image.open(img_path)
                            w, h = img.size
                            if w > 420:
                                ratio = 420.0 / w
                                img = img.resize((420, int(h * ratio)), Image.Resampling.LANCZOS)
                            photo = ImageTk.PhotoImage(img)
                        else:
                            photo = tk.PhotoImage(file=img_path)
                            
                        text_widget.image_create(tk.END, image=photo)
                        text_widget.insert(tk.END, "\n")
                        image_refs_list.append(photo)

                        if filepath:
                            bar_f = tk.Frame(text_widget, bg="#ffffff")
                            setup_widget_ux_helpers(bar_f, text_widget)

                            btn_rep = tk.Button(bar_f, text="✏️ 差し替え", bg="#f1f5f9", fg="#334155", font=("MS Gothic", 8), command=lambda r=rel_path: handle_replace_asset_with_dialog(r))
                            btn_rep.pack(side="left", padx=2)
                            setup_widget_ux_helpers(btn_rep, text_widget, cursor_type="hand2")

                            btn_del = tk.Button(bar_f, text="🗑️ リンク解除", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8), command=lambda r=rel_path: handle_unlink_asset(r))
                            btn_del.pack(side="left", padx=2)
                            setup_widget_ux_helpers(btn_del, text_widget, cursor_type="hand2")

                            text_widget.window_create(tk.END, window=bar_f)
                            text_widget.insert(tk.END, "\n\n")

                    except Exception as e:
                        text_widget.insert(tk.END, f"  [⚠️ 画像読み込み失敗: {fname}]\n")
                else:
                    cand_fname, cand_full_path = find_candidate_lost_asset(rel_path, base_dir)

                    if cand_fname and not is_candidate_dismissed(fname):
                        cand_card = tk.Frame(text_widget, background="#f0f9ff", bd=1, relief="solid", padx=8, pady=6)
                        setup_widget_ux_helpers(cand_card, text_widget)

                        lbl_c = tk.Label(cand_card, text=f"❓ アセット候補あり: 『 {cand_fname} 』", fg="#0284c7", bg="#f0f9ff", font=("MS Gothic", 9, "bold"))
                        lbl_c.pack(side="left")
                        setup_widget_ux_helpers(lbl_c, text_widget)
                        
                        if filepath:
                            btn_fix = tk.Button(
                                cand_card, text="🔍 参照して確定・保存", bg="#0284c7", fg="white", font=("MS Gothic", 8, "bold"), padx=6,
                                command=lambda r=rel_path, c_fp=cand_full_path: handle_replace_asset_with_dialog(r, c_fp)
                            )
                            btn_fix.pack(side="right", padx=5)
                            setup_widget_ux_helpers(btn_fix, text_widget, cursor_type="hand2")

                            btn_dism = tk.Button(
                                cand_card, text="🗑️ 提案削除", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8), padx=4,
                                command=lambda fn=fname: handle_dismiss_candidate(fn)
                            )
                            btn_dism.pack(side="right", padx=2)
                            setup_widget_ux_helpers(btn_dism, text_widget, cursor_type="hand2")

                        text_widget.window_create(tk.END, window=cand_card)
                        text_widget.insert(tk.END, "\n\n")
                    else:
                        text_widget.insert(tk.END, f"  [⚠️ 未確定アセット: {fname}]\n", "quote")
                        if filepath:
                            btn_ins_f = tk.Frame(text_widget, bg="#ffffff")
                            setup_widget_ux_helpers(btn_ins_f, text_widget)

                            btn_ins = tk.Button(
                                btn_ins_f, text="➕ アセットを手動で挿入/選択", bg="#e0f2fe", fg="#0369a1", font=("MS Gothic", 8, "bold"),
                                command=lambda r=rel_path: handle_replace_asset_with_dialog(r)
                            )
                            btn_ins.pack(side="left", padx=2)
                            setup_widget_ux_helpers(btn_ins, text_widget, cursor_type="hand2")

                            btn_dism_ins = tk.Button(
                                btn_ins_f, text="🗑️ リンク解除", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8),
                                command=lambda r=rel_path: handle_unlink_asset(r)
                            )
                            btn_dism_ins.pack(side="left", padx=2)
                            setup_widget_ux_helpers(btn_dism_ins, text_widget, cursor_type="hand2")

                            text_widget.window_create(tk.END, window=btn_ins_f)
                            text_widget.insert(tk.END, "\n\n")
            continue

        doc_match = re.search(r'\[📎\s*添付ファイル:\s*(.*?)\]\((.*?)\)|([\w\-\.\%\s\u3000-\u30ff\u4e00-\u9fff]+\.(?:xlsx|xls|csv|pdf|zip))\b', line, re.IGNORECASE)
        if doc_match:
            fname = doc_match.group(1) or doc_match.group(3)
            rel_path = doc_match.group(2) or f"./assets/{fname}"
            doc_path = os.path.normpath(os.path.join(base_dir, rel_path))

            if os.path.exists(doc_path):
                ext = fname.split(".")[-1].lower() if "." in fname else ""
                icon_str = "📊 Excelワークシート" if ext in ["xlsx", "xls", "csv"] else ("📄 PDFドキュメント" if ext == "pdf" else "📎 添付ファイル")

                doc_card = tk.Frame(text_widget, background="#f8fafc", bd=1, relief="ridge", padx=6, pady=6)
                setup_widget_ux_helpers(doc_card, text_widget)

                lbl_d = tk.Label(doc_card, text=f"{icon_str}: {fname}", fg="#334155", bg="#f8fafc", font=("MS Gothic", 9, "bold"))
                lbl_d.pack(side="left", padx=5)
                setup_widget_ux_helpers(lbl_d, text_widget)

                btn_open = tk.Button(
                    doc_card, text="📂 外部アプリで開く", bg="#0284c7", fg="white", font=("MS Gothic", 8, "bold"),
                    padx=8, pady=3, command=lambda p=doc_path: open_external_app(p)
                )
                btn_open.pack(side="right", padx=5)
                setup_widget_ux_helpers(btn_open, text_widget, cursor_type="hand2")

                if filepath:
                    btn_rep_d = tk.Button(doc_card, text="✏️ 差し替え", bg="#e2e8f0", fg="#334155", font=("MS Gothic", 8), command=lambda r=rel_path: handle_replace_asset_with_dialog(r))
                    btn_rep_d.pack(side="right", padx=2)
                    setup_widget_ux_helpers(btn_rep_d, text_widget, cursor_type="hand2")

                    btn_del_d = tk.Button(doc_card, text="🗑️ リンク解除", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8), command=lambda r=rel_path: handle_unlink_asset(r))
                    btn_del_d.pack(side="right", padx=2)
                    setup_widget_ux_helpers(btn_del_d, text_widget, cursor_type="hand2")

                text_widget.window_create(tk.END, window=doc_card)
                text_widget.insert(tk.END, "\n\n")
            continue

        # 太字装飾 (**...**)
        if "**" in line:
            parts = line.split("**")
            for idx, part in enumerate(parts):
                if idx % 2 == 1:
                    text_widget.insert(tk.END, part, "bold")
                else:
                    text_widget.insert(tk.END, part)
            text_widget.insert(tk.END, "\n")
            continue
            
        text_widget.insert(tk.END, line + "\n")

    # 残りのテーブルバッファの描画
    if table_lines_buffer:
        flush_table_buffer()

    text_widget.config(state="disabled")
    restore_visible_scroll_state(text_widget, scroll_state)

    if progress_bar:
        try:
            progress_bar.stop()
            progress_bar.pack_forget()
        except: pass


class AiReAnchorMarkdownViewerApp:
    """🌟 単体起動テスト用アプリ"""
    def __init__(self, root):
        self.root = root
        self.root.title("AiReAnchor MarkdownViewer - Webコンバーター完全準拠版")
        self.root.geometry("1000x720")
        
        if os.path.exists(ICON_PORTAL):
            try: self.root.iconbitmap(ICON_PORTAL)
            except: pass
            
        self.loaded_file_path = None
        self.image_refs = []
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_safe_exit)
        self.build_ui()

    def build_widgets(self):
        ctrl_f = ttk.Frame(self.root, padding=5)
        ctrl_f.pack(fill="x", side="top")
        
        ttk.Button(ctrl_f, text="📂 Markdownを選択してロード", command=self.choose_and_load_file).pack(side="left", padx=4)
        ttk.Button(ctrl_f, text="🔄 リロード", command=self.refresh_display).pack(side="left", padx=4)
        ttk.Button(ctrl_f, text="🔍 検索 (Ctrl+F)", command=self.toggle_search_widget).pack(side="left", padx=4)
        ttk.Button(ctrl_f, text="📁 アセットフォルダを開く", command=self.open_current_assets_folder).pack(side="left", padx=4)

        self.lbl_char_count = ttk.Label(ctrl_f, text="文字数: 0 文字", font=("MS Gothic", 9, "bold"), foreground="#0284c7")
        self.lbl_char_count.pack(side="left", padx=6)
        
        self.style_var = tk.StringVar(value="rich_md")
        
        rb_s_md = ttk.Radiobutton(ctrl_f, text="シンプル標準MD", variable=self.style_var, value="simple_md", command=self.refresh_display)
        rb_s_md.pack(side="left", padx=3)

        rb_r_md = ttk.Radiobutton(ctrl_f, text="リッチ標準MD", variable=self.style_var, value="rich_md", command=self.refresh_display)
        rb_r_md.pack(side="left", padx=3)

        rb_s_aire = ttk.Radiobutton(ctrl_f, text="AiRe装飾", variable=self.style_var, value="simple_aire", command=self.refresh_display)
        rb_s_aire.pack(side="left", padx=3)

        rb_r_aire = ttk.Radiobutton(ctrl_f, text="リッチAiRe装飾", variable=self.style_var, value="rich_aire", command=self.refresh_display)
        rb_r_aire.pack(side="left", padx=3)

        rb_none = ttk.Radiobutton(ctrl_f, text="装飾OFF(Raw)", variable=self.style_var, value="none", command=self.refresh_display)
        rb_none.pack(side="left", padx=3)
        
        self.img_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_f, text="画像・動画表示", variable=self.img_var, command=self.refresh_display).pack(side="left", padx=6)

        prev_lf = ttk.LabelFrame(self.root, text=" インタラクティブアセット ＆ 昇格修復プレビュー ", padding=10)
        prev_lf.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.text_widget = tk.Text(prev_lf, background="#ffffff", wrap="word")
        self.text_widget.pack(fill="both", expand=True, side="left")
        ysb = ttk.Scrollbar(prev_lf, orient="vertical", command=self.text_widget.yview)
        ysb.pack(side="right", fill="y")
        self.text_widget.configure(yscrollcommand=ysb.set)
        
        self.search_floating_widget = VSCodeFloatingSearchWidget(prev_lf, self.text_widget)

        self.root.bind("<Control-f>", lambda e: self.toggle_search_widget())
        self.root.bind("<Control-F>", lambda e: self.toggle_search_widget())

        self.text_widget.insert(tk.END, "上の「📂 Markdownを選択してロード」ボタンを押してログファイルを読み込ませてください。")
        self.text_widget.config(state="disabled")

    def build_ui(self):
        self.build_widgets()

    def open_current_assets_folder(self):
        base_dir = os.path.dirname(self.loaded_file_path) if self.loaded_file_path else PROJECT_DIR
        open_assets_folder_in_explorer(base_dir)

    def toggle_search_widget(self):
        if self.search_floating_widget.winfo_ismapped():
            self.search_floating_widget.close_widget()
        else:
            self.search_floating_widget.show_at_default_position()

    def choose_and_load_file(self):
        path = filedialog.askopenfilename(title="読み込むMarkdownファイルを選択", filetypes=[("Markdown", "*.md"), ("Text", "*.txt")])
        if path:
            self.loaded_file_path = path
            self.refresh_display()

    def refresh_display(self):
        if not self.loaded_file_path or not os.path.exists(self.loaded_file_path): return
            
        try:
            with open(self.loaded_file_path, "r", encoding="utf-8") as f: content = f.read()
            base_dir = os.path.dirname(self.loaded_file_path)

            self.lbl_char_count.config(text=f"文字数: {len(content):,} 文字")

            render_rich_markdown(
                text_widget=self.text_widget, 
                raw_text=content, 
                base_dir=base_dir, 
                show_rich=(self.style_var.get() != "none"), 
                show_images=self.img_var.get(), 
                image_refs_list=self.image_refs,
                filepath=self.loaded_file_path,
                on_update_callback=self.refresh_display,
                show_style=self.style_var.get()
            )
        except Exception as e:
            messagebox.showerror("エラー", f"ファイルの読み込みに失敗しました: {e}")

    def on_safe_exit(self):
        try:
            for child in self.text_widget.winfo_children():
                try: child.destroy()
                except: pass
        except: pass
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = AiReAnchorMarkdownViewerApp(root)
    root.mainloop()