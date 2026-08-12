# -*- coding: utf-8 -*-
# AiReLinkage.pyw - コンテキスト相補マージ ＆ 採択マネージャー (×ボタン統一・完全決定版)
import os
import sys
import re
import hashlib
import shutil
import ctypes
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Windows AppID 登録
try:
    myappid = 'airelinker.suite.linkage.v22'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
DEFAULT_LOGS_DIR = os.path.join(CURRENT_DIR, "logs")


# 🌟 Windows API を使用してウインドウを OS レベルで最前面に強制フック表示
def force_foreground_window(window):
    try:
        # -1 (ASFW_ANY) で全プロセスからのフォーカス横取りブロックを解除
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
        hwnd = window.winfo_id()
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except: pass
    try:
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
    except: pass


# ================= 🛠 補助関数 =================
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
    """ファイル名の中の数字を数値として正しくソートする（1, 2, 3... 10, 11...）"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def calculate_similarity(str1, str2):
    if not str1 or not str2:
        return 0.0
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


# 🌟 一時ファイル群の自完結クレンジング関数
def cleanup_all_temp_files(scraped_dir, keep_incoming=False):
    temp_files = ["raw_merged_preview.md"]
    temp_dirs = ["merged_preview_assets"]
    
    if not keep_incoming:
        temp_files.extend(["raw_incoming.md", "raw_test.md"])
        temp_dirs.extend(["incoming_assets", "test_assets"])

    for tf in temp_files:
        p = os.path.join(scraped_dir, tf)
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

    for td in temp_dirs:
        p = os.path.join(scraped_dir, td)
        if os.path.exists(p):
            try: shutil.rmtree(p)
            except: pass


# 🌟 マージ成果物を raw_scraped.md ＆ assets/ へ自完結で確定昇格適用
def promote_merged_and_cleanup(chat_folder_path):
    scraped_folder = os.path.join(chat_folder_path, "scraped")
    preview_md_path = os.path.join(scraped_folder, "raw_merged_preview.md")
    preview_assets_dir = os.path.join(scraped_folder, "merged_preview_assets")
    
    master_md_path = os.path.join(scraped_folder, "raw_scraped.md")
    master_assets_dir = os.path.join(scraped_folder, "assets")

    if os.path.exists(preview_md_path):
        shutil.copy2(preview_md_path, master_md_path)
        
        if os.path.exists(preview_assets_dir):
            if os.path.exists(master_assets_dir):
                shutil.rmtree(master_assets_dir)
            shutil.copytree(preview_assets_dir, master_assets_dir)

    # クレンジング実行 (raw_scraped.md と assets/ のみに整理)
    cleanup_all_temp_files(scraped_folder, keep_incoming=False)


# ================= 🌟 相補マージ・アライメントコアエンジン =================
def execute_markdown_alignment_merge(chat_folder_path):
    scraped_folder = os.path.join(chat_folder_path, "scraped")
    old_md_path = os.path.join(scraped_folder, "raw_scraped.md")
    new_md_path = os.path.join(scraped_folder, "raw_incoming.md")
    
    old_assets_dir = os.path.join(scraped_folder, "assets")
    new_assets_dir = os.path.join(scraped_folder, "incoming_assets")

    # 互換フォールバック
    if not os.path.exists(new_md_path):
        fallback_md = os.path.join(scraped_folder, "raw_test.md")
        if os.path.exists(fallback_md):
            new_md_path = fallback_md

    if not os.path.exists(new_assets_dir):
        fallback_assets = os.path.join(scraped_folder, "test_assets")
        if os.path.exists(fallback_assets):
            new_assets_dir = fallback_assets

    if not os.path.exists(new_md_path) and not os.path.exists(old_md_path):
        return False, f"比較対象のMarkdownファイルが見つかりません:\n{new_md_path}"

    scraped_export_dir = os.path.join(chat_folder_path, "scraped")
    assets_export_dir = os.path.join(scraped_export_dir, "merged_preview_assets")
    
    if os.path.exists(assets_export_dir):
        shutil.rmtree(assets_export_dir)
    os.makedirs(assets_export_dir, exist_ok=True)

    # ステップ1: 実体ファイルの自然順ソートによる絶対正解順序の確定
    old_files = sorted([f for f in os.listdir(old_assets_dir) if not f.endswith(".bin")], key=natural_sort_key) if os.path.exists(old_assets_dir) else []
    new_files = sorted([f for f in os.listdir(new_assets_dir) if not f.endswith(".bin")], key=natural_sort_key) if os.path.exists(new_assets_dir) else []

    file_to_hash = {}
    hash_to_ext = {}

    old_hashes = []
    for f in old_files:
        fpath = os.path.join(old_assets_dir, f)
        fh = get_file_md5(fpath)
        if fh:
            ext = f.split(".")[-1].lower() if "." in f else "png"
            file_to_hash[f] = fh
            file_to_hash[f.lower()] = fh
            hash_to_ext[fh] = ext
            if fh not in old_hashes: old_hashes.append(fh)

    new_hashes = []
    for f in new_files:
        fpath = os.path.join(new_assets_dir, f)
        fh = get_file_md5(fpath)
        if fh:
            ext = f.split(".")[-1].lower() if "." in f else "png"
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

    copied_hashes = set()
    for src_dir, file_list in [(old_assets_dir, old_files), (new_assets_dir, new_files)]:
        if not os.path.exists(src_dir): continue
        for f in file_list:
            s_path = os.path.join(src_dir, f)
            fh = get_file_md5(s_path)
            if fh and fh in hash_to_final_fname and fh not in copied_hashes:
                final_fname = hash_to_final_fname[fh]
                d_path = os.path.join(assets_export_dir, final_fname)
                shutil.copy2(s_path, d_path)
                copied_hashes.add(fh)

    # ステップ2: Markdownパース ＆ 旧アセットタグの完全クレンジング
    def parse_md_into_turn_objects(md_path):
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

    old_header, old_turns = parse_md_into_turn_objects(old_md_path)
    new_header, new_turns = parse_md_into_turn_objects(new_md_path)

    if len(old_turns) >= len(new_turns):
        master_turns, sub_turns = list(old_turns), list(new_turns)
        header_to_use = old_header if old_header else new_header
    else:
        master_turns, sub_turns = list(new_turns), list(old_turns)
        header_to_use = new_header if new_header else old_header

    # ステップ3: 相補マージ
    def is_text_anchor_match(t1, t2):
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
            if is_text_anchor_match(sub_turns[i - 1], master_turns[j - 1]):
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    anchors = []
    i, j = n_len, m_len
    while i > 0 and j > 0:
        if is_text_anchor_match(sub_turns[i - 1], master_turns[j - 1]):
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
                if s_turn["asset_files"]:
                    merged.append(s_turn)
                continue
            
            best_idx = -1
            max_sim = 0.0
            for idx, m_turn in enumerate(merged):
                sim = calculate_similarity(s_norm, m_turn["norm_text"])
                if sim > max_sim:
                    max_sim = sim
                    best_idx = idx
            
            if max_sim >= 0.70 and best_idx != -1:
                pass
            else:
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

    output_md_path = os.path.join(scraped_export_dir, "raw_merged_preview.md")
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(full_merged_markdown)

    return True, output_md_path


# ================= 🎛 単体起動用 4アクション選択マネージャー GUI =================
class AiReLinkageActionDialog(ttk.Frame):
    def __init__(self, parent, chat_folder_path=None):
        super().__init__(parent, padding=15)
        self.parent = parent
        self.pack(fill="both", expand=True)

        initial_target = chat_folder_path if (chat_folder_path and os.path.exists(chat_folder_path)) else ""
        self.chat_folder_var = tk.StringVar(value=initial_target)

        # 🌟 ×ボタンで何も選ばずに閉じた場合、マージ一時ファイルのみ削除して4つ保持で安全終了
        self.parent.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.build_ui()
        self.check_folder_validity()

    def on_closing(self):
        chat_folder = self.chat_folder_var.get().strip()
        if chat_folder and os.path.exists(chat_folder):
            scraped_dir = os.path.join(chat_folder, "scraped")
            if os.path.exists(scraped_dir):
                # 🌟 マージ一時ファイル(raw_merged_preview.md / merged_preview_assets/) のみ消去し、既存2つ+新着2つの計4つを保持！
                cleanup_all_temp_files(scraped_dir, keep_incoming=True)
        self.parent.destroy()

    def build_ui(self):
        # 1. チャットフォルダ選択バー
        top_f = ttk.LabelFrame(self, text=" 📂 対象チャットフォルダの指定 ", padding=10)
        top_f.pack(fill="x", pady=(0, 10))

        ttk.Label(top_f, text="チャットフォルダ:").grid(row=0, column=0, sticky="w", padx=5)
        self.entry_folder = ttk.Entry(top_f, textvariable=self.chat_folder_var, width=55)
        self.entry_folder.grid(row=0, column=1, padx=5)
        self.entry_folder.bind("<KeyRelease>", lambda e: self.check_folder_validity())

        ttk.Button(top_f, text="参照...", command=self.browse_folder).grid(row=0, column=2, padx=5)

        self.lbl_status = ttk.Label(top_f, text="⚠️ チャットフォルダを選択してください", font=("MS Gothic", 9, "bold"), foreground="#dc2626")
        self.lbl_status.grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=(5, 0))

        # 2. 4つの決定アクションボタンフレーム
        act_lf = ttk.LabelFrame(self, text=" ⚡ 同期ログの採択決定アクション (1つ選択して適用) ", padding=12)
        act_lf.pack(fill="both", expand=True, pady=5)

        # アクション1: 新着上書き
        self.btn_act1 = tk.Button(
            act_lf, text="① 🆕 新着ログ（赤）で本番ログをそのまま上書き",
            bg="#fee2e2", fg="#991b1b", activebackground="#fecaca", activeforeground="#7f1d1d",
            font=("MS Gothic", 9, "bold"), padx=10, pady=8, bd=1, relief="ridge",
            command=self.action_apply_new_overwrite
        )
        self.btn_act1.pack(fill="x", pady=4)

        # アクション2: 既存維持（新着破棄）
        self.btn_act2 = tk.Button(
            act_lf, text="② 🛡️ 新着データを破棄し、既存ログ（青）を維持",
            bg="#dbeafe", fg="#1e40af", activebackground="#bfdbfe", activeforeground="#1e3a8a",
            font=("MS Gothic", 9, "bold"), padx=10, pady=8, bd=1, relief="ridge",
            command=self.action_discard_new_keep_old
        )
        self.btn_act2.pack(fill="x", pady=4)

        # アクション3: 相補マージ適用
        self.btn_act3 = tk.Button(
            act_lf, text="③ ✨ 相補マージ成果物（緑）を本番ログへ確定適用",
            bg="#dcfce7", fg="#166534", activebackground="#bbf7d0", activeforeground="#14532d",
            font=("MS Gothic", 9, "bold"), padx=10, pady=8, bd=1, relief="ridge",
            command=self.action_apply_merged
        )
        self.btn_act3.pack(fill="x", pady=4)

        # アクション4: 両方保持（保留）
        self.btn_act4 = tk.Button(
            act_lf, text="④ 💬 新旧両方のログ・アセットをそのまま残す（保留）",
            bg="#fef3c7", fg="#92400e", activebackground="#fde68a", activeforeground="#78350f",
            font=("MS Gothic", 9, "bold"), padx=10, pady=8, bd=1, relief="ridge",
            command=self.action_keep_both
        )
        self.btn_act4.pack(fill="x", pady=4)

        # 3. 3画面ビューワー呼出しボタン
        self.btn_viewer = tk.Button(
            self, text="🔍 3画面ビューワー(AiReLinkageViewer)を開いて目視で比較選択",
            bg="#334155", fg="white", activebackground="#475569", activeforeground="white",
            font=("MS Gothic", 9, "bold"), padx=10, pady=8, bd=1, relief="ridge",
            command=self.open_linkage_viewer
        )
        self.btn_viewer.pack(fill="x", pady=(10, 0))

    def browse_folder(self):
        initial_dir = DEFAULT_LOGS_DIR if os.path.exists(DEFAULT_LOGS_DIR) else CURRENT_DIR
        path = filedialog.askdirectory(title="対象のチャットフォルダを選択", initialdir=initial_dir)
        if path:
            self.chat_folder_var.set(path)
            self.check_folder_validity()

    def check_folder_validity(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_dir = os.path.join(chat_folder, "scraped")
        
        valid = False
        if chat_folder and os.path.exists(chat_folder) and os.path.exists(scraped_dir):
            valid = True

        if valid:
            self.lbl_status.config(text=f"✅ チャット『{os.path.basename(chat_folder)}』が正しく読み込まれました", foreground="#166534")
            for btn in [self.btn_act1, self.btn_act2, self.btn_act3, self.btn_act4, self.btn_viewer]:
                btn.config(state="normal")
        else:
            self.lbl_status.config(text="⚠️ 有効なチャットフォルダ（scraped/存在）を選択してください（ボタン無効化中）", foreground="#dc2626")
            for btn in [self.btn_act1, self.btn_act2, self.btn_act3, self.btn_act4, self.btn_viewer]:
                btn.config(state="disabled")

    # ① 新着上書き (raw_scraped.md ＋ assets/ のみに整理自完結)
    def action_apply_new_overwrite(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_dir = os.path.join(chat_folder, "scraped")
        old_md = os.path.join(scraped_dir, "raw_scraped.md")
        new_md = os.path.join(scraped_dir, "raw_incoming.md")
        if not os.path.exists(new_md): new_md = os.path.join(scraped_dir, "raw_test.md")

        new_assets = os.path.join(scraped_dir, "incoming_assets")
        if not os.path.exists(new_assets): new_assets = os.path.join(scraped_dir, "test_assets")

        assets_dir = os.path.join(scraped_dir, "assets")

        if not os.path.exists(new_md):
            messagebox.showwarning("警告", "新着ログ(raw_incoming.md)が見つかりません。")
            return

        if not messagebox.askyesno("上書き確定", "新着データで既存の本番ログ(raw_scraped.md)を丸ごと上書きしますか？\n（一時ファイルはクレンジングされます）"):
            return

        # パス置換上書き
        with open(new_md, "r", encoding="utf-8") as f: inc_txt = f.read()
        scraped_txt = re.sub(r'./incoming_assets/inc_asset_', './assets/asset_', inc_txt)
        with open(old_md, "w", encoding="utf-8") as f: f.write(scraped_txt)

        if os.path.exists(assets_dir):
            shutil.rmtree(assets_dir)
        os.makedirs(assets_dir, exist_ok=True)

        if os.path.exists(new_assets):
            for fname in os.listdir(new_assets):
                sp = os.path.join(new_assets, fname)
                if os.path.isfile(sp):
                    dp = os.path.join(assets_dir, fname.replace("inc_asset_", "asset_"))
                    shutil.copy2(sp, dp)

        # 一時ファイルの削除クレンジング (raw_scraped.md と assets/ のみに整理)
        cleanup_all_temp_files(scraped_dir, keep_incoming=False)
        messagebox.showinfo("成功", f"新着ログで本番ログを上書きし、フォルダ内を raw_scraped.md と assets/ に整理しました！")
        self.parent.destroy()

    # ② 既存維持 (新着破棄自完結)
    def action_discard_new_keep_old(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_dir = os.path.join(chat_folder, "scraped")

        if not messagebox.askyesno("破棄確定", "新着ログデータを破棄して、既存の本番ログをそのまま維持しますか？"):
            return

        cleanup_all_temp_files(scraped_dir, keep_incoming=False)
        messagebox.showinfo("完了", "新着一時データを破棄し、既存の本番ログを維持しました。")
        self.parent.destroy()

    # ③ 相補マージ確定適用 (自完結昇格＆クレンジング)
    def action_apply_merged(self):
        chat_folder = self.chat_folder_var.get().strip()
        scraped_dir = os.path.join(chat_folder, "scraped")

        ok, res_path_or_err = execute_markdown_alignment_merge(chat_folder)
        if not ok:
            messagebox.showerror("マージエラー", res_path_or_err)
            return

        if not messagebox.askyesno("マージ確定", "相補マージ成果物を scraped/raw_scraped.md に確定適用しますか？"):
            return

        # 🌟 マージ成果物を raw_scraped.md ＆ assets/ に確定昇格適用！
        promote_merged_and_cleanup(chat_folder)
        messagebox.showinfo("成功", "相補マージ成果物を本番ログに確定適用し、フォルダ内を整理しました！")
        self.parent.destroy()

    # ④ 両方保持（保留）
    def action_keep_both(self):
        chat_folder = self.chat_folder_var.get().strip()
        if chat_folder and os.path.exists(chat_folder):
            scraped_dir = os.path.join(chat_folder, "scraped")
            if os.path.exists(scraped_dir):
                # マージ一時ファイルのみ削除し、既存2つ+新着2つの計4つを保持
                cleanup_all_temp_files(scraped_dir, keep_incoming=True)
        messagebox.showinfo("保持（保留）", "新旧両方のデータ（raw_scraped.md, assets/, raw_incoming.md, incoming_assets/）を保持したまま終了します。")
        self.parent.destroy()

    def open_linkage_viewer(self):
        chat_folder = self.chat_folder_var.get().strip()
        viewer_script = os.path.join(CURRENT_DIR, "AiReLinkageViewer.pyw")
        if os.path.exists(viewer_script):
            subprocess.Popen([sys.executable, viewer_script, "--chat-folder", chat_folder])
        else:
            messagebox.showerror("エラー", f"AiReLinkageViewer.pyw が見つかりません:\n{viewer_script}")


# ================= 🚀 エントリポイント (背景キック ＆ 最前面ダイアログ起動) =================
if __name__ == "__main__":
    mode_arg = None
    chat_folder_arg = None

    # 引数パース
    if "--chat-folder" in sys.argv:
        idx = sys.argv.index("--chat-folder")
        if idx + 1 < len(sys.argv):
            chat_folder_arg = sys.argv[idx + 1]

    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode_arg = sys.argv[idx + 1]

    # 🌟 モードA: 全自動マージ (auto_merge) ➔ マージ計算 ＋ 確定昇格 ＋ クレンジング ➔ 画面なしで自完結即終了！
    if chat_folder_arg and mode_arg == "auto_merge":
        ok, res = execute_markdown_alignment_merge(chat_folder_arg)
        if ok:
            promote_merged_and_cleanup(chat_folder_arg)
        sys.exit(0)

    # 🌟 モードB: 最前面選択画面表示 (--mode prompt または 単体ダブルクリック起動)
    root = tk.Tk()
    root.title("🔀 AiReLinkage - ログ同期・採択決定マネージャー")
    root.geometry("620x520")
    
    # Windows API によりデスクトップ最前面にポコンと強制フック表示！
    force_foreground_window(root)

    app = AiReLinkageActionDialog(root, chat_folder_path=chat_folder_arg)
    root.mainloop()