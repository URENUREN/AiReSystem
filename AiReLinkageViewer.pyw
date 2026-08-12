# -*- coding: utf-8 -*-
# AiReLinkageViewer.pyw - 3パネルDiff比較 ＆ 統括ミニマップマネージャー (マルチスレッドハッシュ計算並列爆速化版)
import os
import sys
import re
import json
import hashlib
import shutil
import ctypes
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Windows AppID 登録
try:
    myappid = 'airelinker.suite.linkage.v27'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
DEFAULT_LOGS_DIR = os.path.join(CURRENT_DIR, "logs")

# PIL (Pillow) の安全な読み込み
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 高機能マークダウン描画エンジンの安全インポート
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


# ================= 🛠 テキスト＆アセットヘルパー =================
def clean_scraped_ui_noise(text):
    if not text: return ""
    cleaned = re.sub(r'^(?:User|Model)\s+\d{1,2}:\d{2}\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^\s*(?:Thoughts|Expand to view model thoughts|chevron_right|image|Preview unavailable|downloadfullscreen|progress_activity|docs|play_circle)\s*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'<thought>[\s\S]*?</thought>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def normalize_text(text):
    if not text: return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r'\s+', '', text).lower()


def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def calculate_similarity(str1, str2):
    if not str1 or not str2: return 0.0
    set1, set2 = set(str1), set(str2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


def get_file_md5(filepath):
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except:
        return None


def _worker_calc_file_hash(fpath, f, is_new=False):
    """🌟 マルチスレッド用 アセットファイルのMD5ハッシュ一斉計算ワーカー"""
    fh = get_file_md5(fpath)
    if fh:
        ext = f.split(".")[-1].lower() if "." in f else "png"
        return f, fh, ext, is_new
    return None


def cleanup_temp_files(scraped_folder):
    temp_files = ["raw_incoming.md", "raw_test.md", "raw_merged_preview.md"]
    temp_dirs = ["incoming_assets", "test_assets", "merged_preview_assets"]

    for tf in temp_files:
        p = os.path.join(scraped_folder, tf)
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    for td in temp_dirs:
        p = os.path.join(scraped_folder, td)
        if os.path.exists(p):
            try: shutil.rmtree(td)
            except: pass


# ================= 🌟 マージエンジン (scraped/ 完全連携 ＆ 並列ハッシュ照合) =================
def build_merged_context(chat_folder_path):
    scraped_folder = os.path.join(chat_folder_path, "scraped")
    old_md_path = os.path.join(scraped_folder, "raw_scraped.md")
    new_md_path = os.path.join(scraped_folder, "raw_incoming.md")
    
    old_assets_dir = os.path.join(scraped_folder, "assets")
    new_assets_dir = os.path.join(scraped_folder, "incoming_assets")

    if not os.path.exists(new_md_path):
        fallback_md = os.path.join(scraped_folder, "raw_test.md")
        if os.path.exists(fallback_md): new_md_path = fallback_md

    if not os.path.exists(new_assets_dir):
        fallback_assets = os.path.join(scraped_folder, "test_assets")
        if os.path.exists(fallback_assets): new_assets_dir = fallback_assets

    scraped_export_dir = scraped_folder
    assets_export_dir = os.path.join(scraped_export_dir, "merged_preview_assets")

    old_files = sorted([f for f in os.listdir(old_assets_dir) if not f.endswith(".bin")], key=natural_sort_key) if os.path.exists(old_assets_dir) else []
    new_files = sorted([f for f in os.listdir(new_assets_dir) if not f.endswith(".bin")], key=natural_sort_key) if os.path.exists(new_assets_dir) else []

    file_to_hash = {}
    hash_to_ext = {}

    old_hashes = []
    new_hashes = []

    # タスクの準備
    hash_tasks = []
    for f in old_files:
        hash_tasks.append((os.path.join(old_assets_dir, f), f, False))
    for f in new_files:
        hash_tasks.append((os.path.join(new_assets_dir, f), f, True))

    # 🌟 CPUマルチスレッドでMD5ハッシュを一斉並列計算！
    if hash_tasks:
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_worker_calc_file_hash, fpath, f, is_new) for fpath, f, is_new in hash_tasks]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    f, fh, ext, is_new = res
                    if not is_new:
                        file_to_hash[f] = fh
                        file_to_hash[f.lower()] = fh
                        hash_to_ext[fh] = ext
                        if fh not in old_hashes: old_hashes.append(fh)
                    else:
                        file_to_hash[f] = fh
                        file_to_hash[f.lower()] = fh
                        clean_f = f.replace("inc_asset_", "asset_").replace("t_asset_", "asset_")
                        file_to_hash[clean_f] = fh
                        file_to_hash[clean_f.lower()] = fh
                        hash_to_ext[fh] = ext
                        if fh not in new_hashes: new_hashes.append(fh)

    common_anchors = [h for h in new_hashes if h in old_hashes]
    
    master_asset_timeline = []
    last_o, last_n = 0, 0

    for anchor_h in common_anchors:
        o_curr = old_hashes.index(anchor_h)
        n_curr = new_hashes.index(anchor_h)

        for h in old_hashes[last_o:o_curr]:
            if h not in master_asset_timeline: master_asset_timeline.append(h)
        for h in new_hashes[last_n:n_curr]:
            if h not in master_asset_timeline: master_asset_timeline.append(h)

        if anchor_h not in master_asset_timeline:
            master_asset_timeline.append(anchor_h)

        last_o = o_curr + 1
        last_n = n_curr + 1

    for h in old_hashes[last_o:]:
        if h not in master_asset_timeline: master_asset_timeline.append(h)
    for h in new_hashes[last_n:]:
        if h not in master_asset_timeline: master_asset_timeline.append(h)

    hash_to_final_fname = {}
    for idx, fh in enumerate(master_asset_timeline):
        ext = hash_to_ext.get(fh, "png")
        hash_to_final_fname[fh] = f"asset_{idx + 1}.{ext}"

    def parse_turns(md_path):
        turns = []
        header = ""
        if os.path.exists(md_path):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    content = f.read()

                parts = content.split("### ")
                header = parts[0] if len(parts) > 0 else ""
                for et in parts[1:]:
                    lines = et.strip().split("\n")
                    if not lines: continue
                    role_str = "user" if "USER" in lines[0].upper() else "model"
                    disp_head = lines[0].strip()
                    body = "\n".join(lines[1:]).strip()
                    
                    raw_refs = re.findall(r'(\.?(?:/incoming|/test)?/assets/[^\)\]\>\<\s"]+|\b(?:inc_|t_)?asset_\d+\.[a-zA-Z0-9]+)', body)
                    turn_final_assets = []
                    for ref in raw_refs:
                        fname = os.path.basename(ref)
                        clean_fn = fname.replace("inc_asset_", "asset_").replace("t_asset_", "asset_")
                        fh = file_to_hash.get(fname) or file_to_hash.get(fname.lower()) or file_to_hash.get(clean_fn)
                        if fh and fh in hash_to_final_fname:
                            final_fn = hash_to_final_fname[fh]
                            if final_fn not in turn_final_assets:
                                turn_final_assets.append(final_fn)

                    clean_b = re.sub(r'!\s*\[.*?\]\([^\)]*\)', '', body)
                    clean_b = re.sub(r'<(?:video|audio|img)\s+[^>]*src=["\']\.?(?:/incoming|/test)?/assets/[^"\']+["\'][^>]*>(?:</(?:video|audio|img)>)?', '', clean_b, flags=re.IGNORECASE | re.DOTALL)
                    clean_b = clean_scraped_ui_noise(clean_b)

                    turns.append({
                        "role": role_str,
                        "display": disp_head,
                        "clean_text": clean_b,
                        "norm_text": normalize_text(clean_b),
                        "asset_files": turn_final_assets
                    })
            except: pass
        return header, turns

    old_header, old_turns = parse_turns(old_md_path)
    new_header, new_turns = parse_turns(new_md_path)

    if len(old_turns) >= len(new_turns):
        master_turns, sub_turns = list(old_turns), list(new_turns)
        header_to_use = old_header if old_header else new_header
    else:
        master_turns, sub_turns = list(new_turns), list(old_turns)
        header_to_use = new_header if new_header else old_header

    def is_anchor(t1, t2):
        if t1["role"] != t2["role"]: return False
        common = set(t1["asset_files"]).intersection(set(t2["asset_files"]))
        if common: return True
        t1_n, t2_n = t1["norm_text"], t2["norm_text"]
        if len(t1_n) >= 15 and len(t2_n) >= 15:
            return calculate_similarity(t1_n, t2_n) >= 0.75
        return False

    n_len, m_len = len(sub_turns), len(master_turns)
    dp = [[0] * (m_len + 1) for _ in range(n_len + 1)]

    for i in range(1, n_len + 1):
        for j in range(1, m_len + 1):
            if is_anchor(sub_turns[i - 1], master_turns[j - 1]):
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    anchors = []
    i, j = n_len, m_len
    while i > 0 and j > 0:
        if is_anchor(sub_turns[i - 1], master_turns[j - 1]):
            anchors.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    anchors.reverse()

    def merge_segment_turns(seg_sub, seg_master):
        merged = list(seg_master)
        for s_turn in seg_sub:
            s_norm = s_turn["norm_text"]
            if not s_norm or len(s_norm) < 4:
                if s_turn["asset_files"]: merged.append(s_turn)
                continue
            
            best_idx = -1
            max_sim = 0.0
            for idx, m_turn in enumerate(merged):
                sim = calculate_similarity(s_norm, m_turn["norm_text"])
                if sim > max_sim:
                    max_sim = sim
                    best_idx = idx
            
            is_strict = (max_sim >= 0.85) if (s_turn["asset_files"] and best_idx != -1 and merged[best_idx]["asset_files"]) else (max_sim >= 0.65)
            if not is_strict:
                if max_sim >= 0.25 and best_idx != -1:
                    merged.insert(best_idx + 1, s_turn)
                else:
                    merged.append(s_turn)
        return merged

    final_turns = []
    last_s, last_m = 0, 0

    for s_idx, m_idx in anchors:
        seg_s = sub_turns[last_s:s_idx]
        seg_m = master_turns[last_m:m_idx]
        final_turns.extend(merge_segment_turns(seg_s, seg_m))

        anchor_turn = dict(master_turns[m_idx])
        sub_anchor = sub_turns[s_idx]
        for fn in sub_anchor["asset_files"]:
            if fn not in anchor_turn["asset_files"]:
                anchor_turn["asset_files"].append(fn)
        
        final_turns.append(anchor_turn)
        last_s = s_idx + 1
        last_m = m_idx + 1

    final_turns.extend(merge_segment_turns(sub_turns[last_s:], master_turns[last_m:]))

    master_blocks = []
    for obj in final_turns:
        role_disp = "👤 USER" if obj["role"] == "user" else "🤖 MODEL"
        turn_txt = f"### {role_disp}\n"
        if obj["clean_text"]:
            turn_txt += obj["clean_text"] + "\n"

        for fn in obj["asset_files"]:
            ext = fn.split(".")[-1].lower() if "." in fn else "png"
            if ext in ["mp4", "webm"]:
                turn_txt += f'\n<video src="./assets/{fn}" controls width="420"></video>\n'
            else:
                turn_txt += f'\n![添付メディア](./assets/{fn})\n'

        if turn_txt.strip():
            master_blocks.append(turn_txt.strip())

    full_merged_markdown = (header_to_use.strip() if header_to_use else "---") + "\n\n" + "\n\n".join(master_blocks)
    
    return full_merged_markdown, hash_to_final_fname, old_assets_dir, new_assets_dir, old_files, new_files, assets_export_dir, scraped_export_dir, old_turns, new_turns, final_turns


# ================= 🖥️ 統括ミニマップバー付き GUIマネージャー =================
class AiReLinkageGUI:
    def __init__(self, root, chat_folder_path=None):
        self.root = root
        self.root.title("🔀 AiReLinkage - ログ差分比較 ＆ 統括ミニマップマネージャー (爆速化版)")
        self.root.geometry("1400x820")

        default_target = chat_folder_path if (chat_folder_path and os.path.exists(chat_folder_path)) else ""
        self.chat_folder_var = tk.StringVar(value=default_target)

        self.panel_visible = {"old": True, "new": True, "merged": True, "minimap": True}
        self.merged_md_cache = ""
        self.hash_to_final_map = {}
        self.old_assets_dir = ""
        self.new_assets_dir = ""
        self.assets_export_dir = ""
        self.sub_export_dir = ""
        self.old_files = []
        self.new_files = []
        self.old_turns_cache = []
        self.new_turns_cache = []
        self.final_turns_cache = []
        self.img_references = []

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.create_widgets()
        if self.chat_folder_var.get() and os.path.exists(self.chat_folder_var.get()):
            self.load_and_compare()

    def on_closing(self):
        chat_folder = self.chat_folder_var.get().strip()
        if chat_folder and os.path.exists(chat_folder):
            scraped_folder = os.path.join(chat_folder, "scraped")
            prev_md = os.path.join(scraped_folder, "raw_merged_preview.md")
            prev_assets = os.path.join(scraped_folder, "merged_preview_assets")
            
            if os.path.exists(prev_md):
                try: os.remove(prev_md)
                except: pass
            if os.path.exists(prev_assets):
                try: shutil.rmtree(prev_assets)
                except: pass
        
        self.root.destroy()

    def create_widgets(self):
        top_f = ttk.LabelFrame(self.root, text=" 📂 対象チャットフォルダの指定 ", padding=8)
        top_f.pack(fill="x", padx=10, pady=6)

        ttk.Label(top_f, text="チャットフォルダ:").grid(row=0, column=0, sticky="w", padx=5)
        ttk.Entry(top_f, textvariable=self.chat_folder_var, width=70).grid(row=0, column=1, padx=5)
        ttk.Button(top_f, text="参照...", command=self.browse_folder).grid(row=0, column=2, padx=5)
        ttk.Button(top_f, text="🔄 比較読み込み", command=self.load_and_compare).grid(row=0, column=3, padx=10)

        ttk.Button(top_f, text="❓ ミニマップ＆ガイド", command=self.show_help_dialog).grid(row=0, column=4, padx=5)

        tog_f = ttk.Frame(self.root, padding=4)
        tog_f.pack(fill="x", padx=10)

        ttk.Label(tog_f, text="👁️ パネル表示切り替え:", font=("MS PGothic", 9, "bold")).pack(side="left", padx=5)
        self.btn_tog_old = ttk.Button(tog_f, text="📜 既存ログ (青) [ON]", command=lambda: self.toggle_panel("old"))
        self.btn_tog_old.pack(side="left", padx=5)

        self.btn_tog_new = ttk.Button(tog_f, text="🆕 新着ログ (赤) [ON]", command=lambda: self.toggle_panel("new"))
        self.btn_tog_new.pack(side="left", padx=5)

        self.btn_tog_merged = ttk.Button(tog_f, text="✨ マージ提案 (緑) [ON]", command=lambda: self.toggle_panel("merged"))
        self.btn_tog_merged.pack(side="left", padx=5)

        # 3パターンの表示スタイル選択ラジオボタン群
        self.style_var = tk.StringVar(value="simple")
        rb_s = ttk.Radiobutton(tog_f, text="シンプル標準MD", variable=self.style_var, value="simple", command=self.load_and_compare)
        rb_s.pack(side="left", padx=6)

        rb_a = ttk.Radiobutton(tog_f, text="AiRe装飾", variable=self.style_var, value="aire", command=self.load_and_compare)
        rb_a.pack(side="left", padx=4)

        rb_n = ttk.Radiobutton(tog_f, text="装飾OFF(Raw)", variable=self.style_var, value="none", command=self.load_and_compare)
        rb_n.pack(side="left", padx=4)

        self.var_show_media = tk.BooleanVar(value=True)
        ttk.Checkbutton(tog_f, text="🖼️ 画像・動画プレイヤーを表示", variable=self.var_show_media, command=self.load_and_compare).pack(side="right", padx=10)

        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=10, pady=4)

        self.paned = ttk.PanedWindow(main_container, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        self.frame_old = ttk.LabelFrame(self.paned, text=" 📜 既存ログ (scraped/raw_scraped.md) ", padding=5)
        self.text_old = self.create_plain_text_panel(self.frame_old, bg_color="#f0f4f8", fg_color="#1e293b")

        self.frame_new = ttk.LabelFrame(self.paned, text=" 🆕 新着ログ (scraped/raw_incoming.md) ", padding=5)
        self.text_new = self.create_plain_text_panel(self.frame_new, bg_color="#fdf2f2", fg_color="#450a0a")

        self.frame_merged = ttk.LabelFrame(self.paned, text=" ✨ マージ提案成果物 (scraped/raw_merged_preview.md) ", padding=5)
        self.text_merged = self.create_plain_text_panel(self.frame_merged, bg_color="#f0fdf4", fg_color="#064e3b")

        self.frame_minimap = ttk.LabelFrame(self.paned, text=" 📊 全体統括マップ ", padding=2)
        self.canvas_master = tk.Canvas(self.frame_minimap, width=120, background="#f8fafc", highlightthickness=1, highlightbackground="#cbd5e1")
        self.canvas_master.pack(fill="both", expand=True)
        self.canvas_master.bind("<Configure>", lambda e: self.draw_master_minimap())

        self.update_panel_layout()

        for txt in [self.text_old, self.text_new, self.text_merged]:
            txt.bind("<KeyRelease>", lambda e: self.draw_master_minimap())
            txt.bind("<MouseWheel>", lambda e: self.root.after(10, self.draw_master_minimap))

        act_f = ttk.LabelFrame(self.root, text=" ⚡ 統合決定アクション (選択した内容で scraped/ 本番ログを更新) ", padding=8)
        act_f.pack(fill="x", padx=10, pady=6)

        btn_keep_old = tk.Button(
            act_f, text="🛡️ 既存ログ（青）を維持（新着データを破棄）",
            bg="#dbeafe", fg="#1e40af", activebackground="#bfdbfe", activeforeground="#1e3a8a",
            font=("MS PGothic", 9, "bold"), padx=12, pady=6, bd=1, relief="ridge", command=self.discard_new_choice
        )
        btn_keep_old.pack(side="left", padx=10)

        btn_apply_new = tk.Button(
            act_f, text="🆕 新着データ（赤）で本番ログをそのまま上書き",
            bg="#fee2e2", fg="#991b1b", activebackground="#fecaca", activeforeground="#7f1d1d",
            font=("MS PGothic", 9, "bold"), padx=12, pady=6, bd=1, relief="ridge", command=self.apply_new_choice
        )
        btn_apply_new.pack(side="left", padx=10)

        btn_apply_merged = tk.Button(
            act_f, text="✨ マージ提案（緑）を採用して scraped/raw_scraped.md に確定適用",
            bg="#dcfce7", fg="#166534", activebackground="#bbf7d0", activeforeground="#14532d",
            font=("MS PGothic", 10, "bold"), padx=14, pady=6, bd=1, relief="ridge", command=self.apply_merged_choice
        )
        btn_apply_merged.pack(side="right", padx=10)

    def create_plain_text_panel(self, parent_frame, bg_color, fg_color):
        container = ttk.Frame(parent_frame)
        container.pack(fill="both", expand=True)

        txt = tk.Text(container, background=bg_color, fg=fg_color, font=("MS Gothic", 10), wrap="word")
        txt.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(container, command=txt.yview)
        sb.pack(fill="y", side="right")
        txt.config(yscrollcommand=sb.set)

        return txt

    def draw_master_minimap(self):
        canvas = self.canvas_master
        canvas.delete("all")
        h = canvas.winfo_height()
        w = canvas.winfo_width()
        if h <= 0 or w <= 0: return

        content = self.text_merged.get("1.0", tk.END)
        lines = content.split("\n")
        total_lines = len(lines)
        if total_lines == 0: return

        line_h = max(1, h / total_lines)

        for idx, line in enumerate(lines):
            y = idx * line_h
            if "![添付" in line or "<video" in line:
                canvas.create_line(30, y, max(35, w - 10), y, fill="#ffffff", width=2)
                canvas.create_line(30, y+1, max(35, w - 10), y+1, fill="#38bdf8", width=1)
            elif "### " in line:
                canvas.create_line(35, y, max(40, w - 15), y, fill="#475569", width=1)
            else:
                canvas.create_line(40, y, max(45, w - 20), y, fill="#cbd5e1", width=1)

        if self.final_turns_cache:
            turn_cnt = len(self.final_turns_cache)
            for idx, turn in enumerate(self.final_turns_cache):
                y1 = (idx / turn_cnt) * h
                y2 = ((idx + 1) / turn_cnt) * h
                
                has_in_old = any(calculate_similarity(turn["norm_text"], ot["norm_text"]) >= 0.70 for ot in self.old_turns_cache) if self.old_turns_cache else False
                if has_in_old:
                    canvas.create_rectangle(4, y1, 14, y2, fill="#3b82f6", outline="")

                has_in_new = any(calculate_similarity(turn["norm_text"], nt["norm_text"]) >= 0.70 for nt in self.new_turns_cache) if self.new_turns_cache else False
                if has_in_new:
                    canvas.create_rectangle(16, y1, 26, y2, fill="#ef4444", outline="")

        top_index = self.text_merged.index("@0,0")
        bot_index = self.text_merged.index(f"@0,{self.text_merged.winfo_height()}")
        top_line = int(top_index.split(".")[0])
        bot_line = int(bot_index.split(".")[0])

        fy1 = (top_line / total_lines) * h
        fy2 = (bot_line / total_lines) * h
        canvas.create_rectangle(2, fy1, max(30, w - 2), fy2, fill="", outline="#2563eb", width=2)

    def show_help_dialog(self):
        help_win = tk.Toplevel(self.root)
        help_win.title("❓ ミニマップ ＆ ガイド解説")
        help_win.geometry("560x480")

        f = ttk.Frame(help_win, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="📊 🔀 AiReLinkage ガイド ＆ 統括ミニマップの見方", font=("MS Gothic", 10, "bold")).pack(anchor="w", pady=(0, 6))

        txt_frame = ttk.Frame(f)
        txt_frame.pack(fill="both", expand=True, pady=4)

        txt = tk.Text(txt_frame, wrap="word", font=("MS Gothic", 9), background="#ffffff", relief="solid", bd=1)
        sb = ttk.Scrollbar(txt_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        guide_txt = """======================================================================
 🔀 AiReLinkage - 差分比較 ＆ 統括ミニマップ使い方マニュアル
======================================================================

【1. このツールで何ができるのか？】
 既存の本番ログ (raw_scraped.md) と、新しく届いた差分ログ (raw_incoming.md)
 の内容をリアルタイムで3パネル比較し、2つの会話ログの重なり合いを
 自動で繋ぎ合わせた「マージ提案成果物」をプレビュー・確定適用するツールです。

【2. 3つの比較パネルの意味】
 📜 既存ログ (青パネル): これまで保存されていた本番データ。
 🆕 新着ログ (赤パネル): ブラウザ等から新しく届いた差分データ。
 ✨ マージ提案 (緑パネル): 既存と新着の重複を排除し、完全統合された最新データ。

【3. 右端「統括ミニマップ」のマークの見方】
 🔵 左側の青マーカー帯 : 既存ログ (raw_scraped.md) に含まれる会話範囲
 🔴 隣の赤マーカー帯 : 新着ログ (raw_incoming.md) に含まれる会話範囲
 ⚪ 右側の白い横線マーク : 画像や動画メディアが配置されている位置
 🔳 青い四角枠         : 現在画面上に表示されているスクロール範囲

【4. ⚡ 3つの統合決定アクション（どれを押せばいいか？）】
 ✨【マージ提案を採用（一番推奨）】:
   既存(青)と新着(赤)を重ね合わせ統合し、本番ログ(raw_scraped.md)を更新します。
   同時に一時ファイル(raw_incoming.md等)を自動で全消去整理します。

 🆕【新着データでそのまま上書き】:
   既存ログを捨て、今回届いた新しいデータで丸ごと上書き保存します。

 🛡️【既存ログを維持】:
   新着データを破棄し、大切な既存の古いログを守ります。
======================================================================
"""
        txt.insert(tk.END, guide_txt)
        txt.config(state="disabled")

        ttk.Button(f, text="閉じる", command=help_win.destroy).pack(anchor="e", pady=(8, 0))

    def toggle_panel(self, panel_key):
        self.panel_visible[panel_key] = not self.panel_visible[panel_key]
        self.update_panel_layout()

    def update_panel_layout(self):
        for child in self.paned.panes():
            self.paned.forget(child)

        if self.panel_visible.get("old", True):
            self.paned.add(self.frame_old, weight=3)
            self.btn_tog_old.config(text="📜 既存ログ (青) [ON]")
        else:
            self.btn_tog_old.config(text="📜 既存ログ (青) [OFF]")

        if self.panel_visible.get("new", True):
            self.paned.add(self.frame_new, weight=3)
            self.btn_tog_new.config(text="🆕 新着ログ (赤) [ON]")
        else:
            self.btn_tog_new.config(text="🆕 新着ログ (赤) [OFF]")

        if self.panel_visible.get("merged", True):
            self.paned.add(self.frame_merged, weight=3)
            self.btn_tog_merged.config(text="✨ マージ提案 (緑) [ON]")
        else:
            self.btn_tog_merged.config(text="✨ マージ提案 (緑) [OFF]")

        if self.panel_visible.get("minimap", True):
            self.paned.add(self.frame_minimap, weight=1)

    def browse_folder(self):
        initial_dir = DEFAULT_LOGS_DIR if os.path.exists(DEFAULT_LOGS_DIR) else CURRENT_DIR
        path = filedialog.askdirectory(title="対象のチャットフォルダを選択", initialdir=initial_dir)
        if path:
            self.chat_folder_var.set(path)
            self.load_and_compare()

    def render_rich_media_content(self, text_widget, raw_content, base_assets_dir, target_md_filepath=None):
        current_style = self.style_var.get()
        show_media = self.var_show_media.get()

        render_rich_markdown(
            text_widget=text_widget,
            raw_text=raw_content,
            base_dir=base_assets_dir,
            show_rich=(current_style != "none"),
            show_images=show_media,
            image_refs_list=self.img_references,
            filepath=target_md_filepath,
            show_style=current_style
        )

    def _worker_copy_file(self, sp, dp):
        """🌟 アセット複製用並列スレッドワーカー"""
        try:
            shutil.copy2(sp, dp)
            return True
        except:
            return False

    def load_and_compare(self):
        self.img_references.clear()
        chat_folder = self.chat_folder_var.get().strip()
        if not chat_folder or not os.path.exists(chat_folder):
            return

        scraped_folder = os.path.join(chat_folder, "scraped")
        old_md_path = os.path.join(scraped_folder, "raw_scraped.md")
        new_md_path = os.path.join(scraped_folder, "raw_incoming.md")
        if not os.path.exists(new_md_path):
            fallback_md = os.path.join(scraped_folder, "raw_test.md")
            if os.path.exists(fallback_md): new_md_path = fallback_md

        old_assets = os.path.join(scraped_folder, "assets")
        new_assets = os.path.join(scraped_folder, "incoming_assets")
        if not os.path.exists(new_assets):
            fallback_assets = os.path.join(scraped_folder, "test_assets")
            if os.path.exists(fallback_assets): new_assets = fallback_assets

        preview_md_path = os.path.join(scraped_folder, "raw_merged_preview.md")
        preview_assets_dir = os.path.join(scraped_folder, "merged_preview_assets")

        # 1. 既存ログのロード
        old_text = ""
        if os.path.exists(old_md_path):
            with open(old_md_path, "r", encoding="utf-8") as f: old_text = f.read()
        self.render_rich_media_content(self.text_old, old_text, scraped_folder, old_md_path)

        # 2. 新着ログのロード
        new_text = ""
        if os.path.exists(new_md_path):
            with open(new_md_path, "r", encoding="utf-8") as f: new_text = f.read()
        self.render_rich_media_content(self.text_new, new_text, scraped_folder, new_md_path)

        # 3. scrapedマージ提案の計算＆描画 (マルチスレッドハッシュ計算エンジンで爆速化)
        if os.path.exists(new_md_path) or os.path.exists(old_md_path):
            res_md, h_map, o_dir, n_dir, o_f, n_f, exp_a_dir, scraped_exp_dir, o_turns, n_turns, f_turns = build_merged_context(chat_folder)
            self.merged_md_cache = res_md
            self.hash_to_final_map = h_map
            self.old_assets_dir = o_dir
            self.new_assets_dir = n_dir
            self.assets_export_dir = exp_a_dir
            self.old_files = o_f
            self.new_files = n_f
            self.old_turns_cache = o_turns
            self.new_turns_cache = n_turns
            self.final_turns_cache = f_turns

            os.makedirs(scraped_exp_dir, exist_ok=True)
            with open(preview_md_path, "w", encoding="utf-8") as f:
                f.write(res_md)

            # 🌟 アセットコピーもマルチスレッドで並列処理化
            os.makedirs(exp_a_dir, exist_ok=True)
            copy_tasks = []
            copied = set()

            for src_dir, flist in [(o_dir, o_f), (n_dir, n_f)]:
                if not os.path.exists(src_dir): continue
                for f in flist:
                    sp = os.path.join(src_dir, f)
                    fh = get_file_md5(sp)
                    if fh and fh in h_map and fh not in copied:
                        fn = h_map[fh]
                        dp = os.path.join(exp_a_dir, fn)
                        copy_tasks.append((sp, dp))
                        copied.add(fh)

            if copy_tasks:
                max_workers = min(32, (os.cpu_count() or 4) * 2)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(self._worker_copy_file, sp, dp) for sp, dp in copy_tasks]
                    for _ in as_completed(futures): pass

            self.render_rich_media_content(self.text_merged, res_md, scraped_folder, preview_md_path)
        else:
            self.render_rich_media_content(self.text_merged, "", scraped_folder, None)

        self.root.after(100, self.draw_master_minimap)

    def apply_merged_choice(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_folder = os.path.join(chat_folder, "scraped")
        old_md_path = os.path.join(scraped_folder, "raw_scraped.md")
        assets_export_dir = os.path.join(scraped_folder, "assets")
        
        preview_md_path = os.path.join(scraped_folder, "raw_merged_preview.md")
        preview_assets_dir = os.path.join(scraped_folder, "merged_preview_assets")

        if not os.path.exists(preview_md_path):
            messagebox.showwarning("警告", "適用できるマージデータがありません。")
            return

        if not messagebox.askyesno("確定確認", "マージ成果物を scraped/raw_scraped.md に確定適用しますか？\n（一時ファイルは削除され、本番2つのみに整理されます）"):
            return

        shutil.copy2(preview_md_path, old_md_path)
        
        os.makedirs(assets_export_dir, exist_ok=True)
        if os.path.exists(preview_assets_dir):
            copy_tasks = []
            for f in os.listdir(preview_assets_dir):
                sp = os.path.join(preview_assets_dir, f)
                dp = os.path.join(assets_export_dir, f)
                copy_tasks.append((sp, dp))

            if copy_tasks:
                max_workers = min(32, (os.cpu_count() or 4) * 2)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(self._worker_copy_file, sp, dp) for sp, dp in copy_tasks]
                    for _ in as_completed(futures): pass

        cleanup_temp_files(scraped_folder)

        messagebox.showinfo("成功", f"マージ成果物を本番ログに確定適用し、フォルダ内を raw_scraped.md と assets/ に整理しました！")
        self.load_and_compare()

    def apply_new_choice(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_folder = os.path.join(chat_folder, "scraped")
        old_md_path = os.path.join(scraped_folder, "raw_scraped.md")
        new_md_path = os.path.join(scraped_folder, "raw_incoming.md")
        if not os.path.exists(new_md_path): new_md_path = os.path.join(scraped_folder, "raw_test.md")

        new_assets_dir = os.path.join(scraped_folder, "incoming_assets")
        if not os.path.exists(new_assets_dir): new_assets_dir = os.path.join(scraped_folder, "test_assets")

        assets_export_dir = os.path.join(scraped_folder, "assets")

        if not os.path.exists(new_md_path):
            messagebox.showwarning("警告", "新着データ raw_incoming.md がありません。")
            return

        if not messagebox.askyesno("上書き確認", "新着データで既存の raw_scraped.md を丸ごと上書きしますか？"):
            return

        with open(new_md_path, "r", encoding="utf-8") as f:
            inc_txt = f.read()
        scraped_txt = re.sub(r'./incoming_assets/inc_asset_', './assets/asset_', inc_txt)
        with open(old_md_path, "w", encoding="utf-8") as f:
            f.write(scraped_txt)

        if os.path.exists(assets_export_dir):
            shutil.rmtree(assets_export_dir)
        os.makedirs(assets_export_dir, exist_ok=True)

        if os.path.exists(new_assets_dir):
            copy_tasks = []
            for fname in os.listdir(new_assets_dir):
                sp = os.path.join(new_assets_dir, fname)
                if os.path.isfile(sp):
                    dp = os.path.join(assets_export_dir, fname.replace("inc_asset_", "asset_"))
                    copy_tasks.append((sp, dp))

            if copy_tasks:
                max_workers = min(32, (os.cpu_count() or 4) * 2)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(self._worker_copy_file, sp, dp) for sp, dp in copy_tasks]
                    for _ in as_completed(futures): pass

        cleanup_temp_files(scraped_folder)

        messagebox.showinfo("成功", "新着データで本番ログを上書き保存し、フォルダ内を整理しました。")
        self.load_and_compare()

    def discard_new_choice(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_folder = os.path.join(chat_folder, "scraped")

        if not messagebox.askyesno("破棄確認", "新着一時データを破棄して、既存ログをそのまま維持しますか？"):
            return

        cleanup_temp_files(scraped_folder)

        messagebox.showinfo("完了", "一時データを破棄し、既存ログをそのまま維持しました。")
        self.load_and_compare()


if __name__ == "__main__":
    chat_folder_arg = None
    if len(sys.argv) > 1 and sys.argv[1] == "--chat-folder":
        chat_folder_arg = sys.argv[2]

    try:
        root = tk.Tk()
        app = AiReLinkageGUI(root, chat_folder_path=chat_folder_arg)
        root.mainloop()
    except Exception as e:
        root_err = tk.Tk()
        root_err.withdraw()
        messagebox.showerror("AiReLinkageViewer 起動エラー", f"プログラムの起動中に例外が発生しました:\n{e}")