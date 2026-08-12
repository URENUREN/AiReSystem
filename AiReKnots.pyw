# -*- coding: utf-8 -*-
# AiReKnots.pyw - マルチソース・ログ自動統合 ＆ 構造ビジュアライザー (文脈位置追従・アセット正常配置版)
import os
import sys
import json
import re
import datetime
import hashlib
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 🌟 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_KNOTS = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

try:
    import ctypes
    myappid = 'airelinker.suite.knots.v13'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except: pass


def get_file_md5(filepath):
    """ファイルのMD5ハッシュ値を計算"""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except:
        return None


def calculate_similarity(str1, str2):
    """Jaccard類似度によるテキスト一致率算出"""
    if not str1 or not str2: return 0.0
    set1, set2 = set(str1), set(str2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


def clean_scraped_ui_noise(text):
    """UIゴミテキストやノイズの徹底除去"""
    if not text: return ""
    cleaned = re.sub(r'^(?:User|Model)\s+\d{1,2}:\d{2}\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^\s*(?:Thoughts|Expand to view model thoughts|chevron_right|image|Preview unavailable|downloadfullscreen|progress_activity|docs|play_circle)\s*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'<thought>[\s\S]*?</thought>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def normalize_text(text):
    """テキストの改行・空白を除去して正規化比較用文字列を作成"""
    if not text: return ""
    text = clean_scraped_ui_noise(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r'\s+', '', text).lower()


class AiReKnotsEngine:
    """🌟 AiReLinkage相補マージ ＆ MD5アセット一元化 融合エンジン"""
    def __init__(self, config=None):
        self.config = config if config else load_config()

    def scan_chat_sources(self, chat_folder_path):
        """チャットフォルダ配下にある全ソースを自動検出"""
        sources = {
            "master": {"has_md": False, "raw_filepath": None, "folder_path": chat_folder_path},
            "importer": {"has_md": False, "raw_filepath": None, "folder_path": None, "assets_path": None},
            "scraped": {"has_md": False, "raw_filepath": None, "folder_path": None, "assets_path": None},
            "3rd": {"has_md": False, "raw_filepath": None, "folder_path": None, "assets_path": None}
        }

        if not os.path.exists(chat_folder_path) or not os.path.isdir(chat_folder_path):
            return sources

        master_raw = os.path.join(chat_folder_path, "raw_master.md")
        if os.path.exists(master_raw):
            sources["master"]["has_md"] = True
            sources["master"]["raw_filepath"] = master_raw

        for item in os.listdir(chat_folder_path):
            item_path = os.path.join(chat_folder_path, item)
            if os.path.isdir(item_path) and item not in ["assets", "my_documents", "my_forge", "master"]:
                src_key = item
                if src_key not in sources:
                    sources[src_key] = {"has_md": False, "raw_filepath": None, "folder_path": item_path, "assets_path": None}

                sources[src_key]["folder_path"] = item_path
                
                for f in os.listdir(item_path):
                    if f.endswith(".md") and not f.startswith("summary"):
                        sources[src_key]["has_md"] = True
                        sources[src_key]["raw_filepath"] = os.path.join(item_path, f)
                        break

                assets_dir = os.path.join(item_path, "assets")
                sources[src_key]["assets_path"] = assets_dir

        return sources

    def get_chat_signal_data(self, chat_folder_path):
        """ポータル連携用のシグナルメタデータを出力"""
        sources = self.scan_chat_sources(chat_folder_path)
        chat_name = os.path.basename(chat_folder_path)
        canonical_service = "AI Service"

        for s_key, s_info in sources.items():
            raw_p = s_info.get("raw_filepath")
            if raw_p and os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8") as f: content = f.read()
                    m_svc = re.search(r'ai_service:\s*"([^"]+)"', content)
                    if m_svc:
                        canonical_service = m_svc.group(1)
                        break
                except: pass

        return {
            "chat_title": chat_name,
            "canonical_service": canonical_service,
            "sources": sources
        }

    def _get_time_span_seconds(self, raw_filepath):
        """rawファイルから true_start_time と true_end_time の時間幅（秒数）を算出"""
        if not raw_filepath or not os.path.exists(raw_filepath): return 0
        try:
            with open(raw_filepath, "r", encoding="utf-8") as f: content = f.read(3000)
            m_s = re.search(r'true_start_time:\s*"([^"]+)"', content)
            m_e = re.search(r'true_end_time:\s*"([^"]+)"', content)
            if m_s and m_e:
                st = datetime.datetime.strptime(m_s.group(1), "%Y-%m-%d %H:%M:%S")
                et = datetime.datetime.strptime(m_e.group(1), "%Y-%m-%d %H:%M:%S")
                return max(0, (et - st).total_seconds())
        except: pass
        return 0

    def _sort_sources_by_priority(self, sources, priority_mode):
        """タイムスパン最大優先によるソースの優先順位決定"""
        items = list(sources.items())
        if priority_mode == "timespan_first" or priority_mode == "most_info":
            items.sort(
                key=lambda x: (
                    self._get_time_span_seconds(x[1]["raw_filepath"]),
                    os.path.getsize(x[1]["raw_filepath"]) if x[1]["raw_filepath"] and os.path.exists(x[1]["raw_filepath"]) else 0
                ),
                reverse=True
            )
        elif priority_mode == "importer_first":
            items.sort(key=lambda x: 0 if x[0] == "importer" else (1 if x[0] == "scraped" else 2))
        elif priority_mode == "scraped_first":
            items.sort(key=lambda x: 0 if x[0] == "scraped" else (1 if x[0] == "importer" else 2))
        elif priority_mode == "latest":
            items.sort(key=lambda x: os.path.getmtime(x[1]["raw_filepath"]) if x[1]["raw_filepath"] and os.path.exists(x[1]["raw_filepath"]) else 0, reverse=True)
        else:
            items.sort(key=lambda x: os.path.getsize(x[1]["raw_filepath"]) if x[1]["raw_filepath"] and os.path.exists(x[1]["raw_filepath"]) else 0, reverse=True)
        return items

    def _build_asset_hash_map(self, chat_folder_path):
        """全ソースのアセットファイルをマッピング"""
        sources = self.scan_chat_sources(chat_folder_path)
        hash_map = {}

        for s_key, s_info in sources.items():
            if s_key == "master": continue
            a_dir = s_info.get("assets_path")
            if a_dir and os.path.exists(a_dir):
                try:
                    for fn in os.listdir(a_dir):
                        fp = os.path.join(a_dir, fn)
                        if os.path.isfile(fp) and not fn.endswith(".bin"):
                            f_hash = get_file_md5(fp)
                            hash_map[fn] = {
                                "src_name": s_key,
                                "rel_path": f"./{s_key}/assets/{fn}",
                                "filename": fn,
                                "full_path": fp,
                                "hash": f_hash
                            }
                except: pass
        return hash_map

    def _extract_media_filenames(self, text):
        """🌟 マークダウン/HTMLテキスト内からアセットファイル名を確実に抽出"""
        if not text: return []
        filenames = []
        matches = re.findall(r'(?:!\[.*?\]\((.*?)\)|<[a-z]+\s+[^>]*?src=["\'](.*?)["\'][^>]*?>)', text, re.IGNORECASE)
        for m in matches:
            raw_path = m[0] if m[0] else m[1]
            if raw_path:
                fn = os.path.basename(raw_path.strip().replace("\\", "/").split("?")[0])
                if re.search(r'\.(?:png|jpg|jpeg|gif|webp|svg|mp3|wav|mp4|webm)$', fn, re.IGNORECASE):
                    if fn not in filenames:
                        filenames.append(fn)
        return filenames

    def _split_into_turns(self, content):
        """🌟 あらゆるソースの発言ヘッダーを吸収する万能ターンスプリッター"""
        if not content: return "", []
        
        parts = content.split("---")
        yaml_header = ""
        body_content = content
        if len(parts) >= 3:
            yaml_header = f"---{parts[1]}---"
            body_content = "---".join(parts[2:])

        pattern = r'(?=(?:^|\n)(?:###\s*|□\s*ユーザー|■\s*AI|\[■\]\s*|👤\s*USER|🤖\s*MODEL|\bUser:|\bModel:))'
        raw_blocks = re.split(pattern, body_content, flags=re.IGNORECASE)

        parsed_turns = []
        for block in raw_blocks:
            cleaned_block = block.strip()
            if not cleaned_block or cleaned_block.startswith("# 🌟") or cleaned_block.startswith("> ⚓"):
                continue

            lines = cleaned_block.split("\n")
            first_line = lines[0].upper()
            
            role = "user"
            if "MODEL" in first_line or "AI" in first_line or "■" in first_line:
                role = "model"
            elif "USER" in first_line or "ユーザー" in first_line or "□" in first_line:
                role = "user"

            body_text = "\n".join(lines[1:]).strip() if len(lines) > 1 else cleaned_block
            media_fns = self._extract_media_filenames(cleaned_block)

            clean_body = re.sub(r'!\s*\[.*?\]\([^\)]*\)', '', body_text)
            clean_body = re.sub(r'<(?:video|audio|img)\s+[^>]*src=["\'][^"\']+["\'][^>]*>(?:</(?:video|audio|img)>)?', '', clean_body, flags=re.IGNORECASE | re.DOTALL)
            clean_body = clean_scraped_ui_noise(clean_body)

            parsed_turns.append({
                "role": role,
                "clean_text": clean_body,
                "norm_text": normalize_text(clean_body),
                "media_filenames": media_fns,
                "raw_block": cleaned_block
            })

        return yaml_header, parsed_turns

    def build_integrated_master(self, chat_folder_path, is_export_master=False):
        """🌟 文脈位置追従・アセット位置完全補正マスター構築処理"""
        try:
            sources = self.scan_chat_sources(chat_folder_path)
            priority_mode = self.config.get("knots_priority_mode", "timespan_first")

            sub_sources = {k: v for k, v in sources.items() if k != "master" and v["has_md"]}
            if not sub_sources:
                return None, "有効なソースログが見つかりません。"

            sorted_sources = self._sort_sources_by_priority(sub_sources, priority_mode)
            asset_hash_map = self._build_asset_hash_map(chat_folder_path)

            primary_src_name, primary_src_info = sorted_sources[0]
            primary_raw = primary_src_info.get("raw_filepath")

            if not primary_raw or not os.path.exists(primary_raw):
                return None, "主軸ソースファイルが見つかりません。"

            with open(primary_raw, "r", encoding="utf-8") as f:
                primary_content = f.read()

            yaml_header, primary_turns = self._split_into_turns(primary_content)

            master_service_name = "AI Service"
            m_svc = re.search(r'ai_service:\s*"([^"]+)"', primary_content)
            if m_svc: master_service_name = m_svc.group(1)

            master_start_time = "不明"
            master_end_time = "不明"
            m_s = re.search(r'true_start_time:\s*"([^"]+)"', primary_content)
            m_e = re.search(r'true_end_time:\s*"([^"]+)"', primary_content)
            if m_s: master_start_time = m_s.group(1)
            if m_e: master_end_time = m_e.group(1)

            other_turns_list = []
            for src_name, src_info in sorted_sources[1:]:
                raw_p = src_info.get("raw_filepath")
                if raw_p and os.path.exists(raw_p):
                    try:
                        with open(raw_p, "r", encoding="utf-8") as f: c = f.read()
                        _, p_turns = self._split_into_turns(c)
                        other_turns_list.append((src_name, p_turns))
                    except: pass

            merged_turns = []
            for p_turn in primary_turns:
                turn_copy = dict(p_turn)
                turn_copy["formatted_media"] = []
                merged_turns.append(turn_copy)

            seen_media_filenames = set()

            # 1. 主軸ターン自身の画像処理
            for turn in merged_turns:
                for fn in turn.get("media_filenames", []):
                    if fn not in seen_media_filenames:
                        seen_media_filenames.add(fn)
                        asset_info = asset_hash_map.get(fn, {})
                        target_path = asset_info.get("rel_path", f"./{primary_src_name}/assets/{fn}")

                        if fn.lower().endswith((".mp4", ".webm")):
                            turn["formatted_media"].append(f'<video src="{target_path}" controls width="420"></video>')
                        else:
                            turn["formatted_media"].append(f'![添付メディア]({target_path})')

            # 🌟 2. 他ソース（scraped等）からのアセット位置追従補完！
            for o_src_name, o_turns in other_turns_list:
                last_matched_master_idx = 0  # 最後に会話が一致した主軸の位置アンカー

                for o_turn in o_turns:
                    media_fns = o_turn.get("media_filenames", [])

                    # テキスト本文が存在するターンであれば、主軸との一致位置（アンカー）を更新
                    if o_turn["norm_text"]:
                        best_idx = -1
                        max_sim = 0.0
                        for m_idx, m_turn in enumerate(merged_turns):
                            if m_turn["role"] == o_turn["role"]:
                                sim = calculate_similarity(o_turn["norm_text"], m_turn["norm_text"])
                                if sim > max_sim:
                                    max_sim = sim
                                    best_idx = m_idx
                        if max_sim >= 0.35 and best_idx != -1:
                            last_matched_master_idx = best_idx

                    # 画像・メディアが含まれるターンの補完指定！
                    if media_fns:
                        target_idx = -1
                        # A. テキストがある場合はテキスト類似度で検索
                        if o_turn["norm_text"]:
                            best_idx = -1
                            max_sim = 0.0
                            for m_idx, m_turn in enumerate(merged_turns):
                                if m_turn["role"] == o_turn["role"]:
                                    sim = calculate_similarity(o_turn["norm_text"], m_turn["norm_text"])
                                    if sim > max_sim:
                                        max_sim = sim
                                        best_idx = m_idx
                            if max_sim >= 0.25 and best_idx != -1:
                                target_idx = best_idx

                        # B. テキストが空の画像単独ターンの場合、直前の会話アンカー位置 (last_matched_master_idx) を親ターンに決定！
                        if target_idx == -1:
                            target_idx = last_matched_master_idx

                        # 正しい位置のターンへアセットを追加
                        if 0 <= target_idx < len(merged_turns):
                            target_turn = merged_turns[target_idx]
                            for fn in media_fns:
                                if fn not in seen_media_filenames:
                                    seen_media_filenames.add(fn)
                                    asset_info = asset_hash_map.get(fn, {})
                                    target_path = asset_info.get("rel_path", f"./{o_src_name}/assets/{fn}")

                                    if fn.lower().endswith((".mp4", ".webm")):
                                        target_turn["formatted_media"].append(f'<video src="{target_path}" controls width="420"></video>')
                                    else:
                                        target_turn["formatted_media"].append(f'![添付メディア]({target_path})')

            # 3. 最終テキストブロックの構築
            master_blocks = []
            for turn in merged_turns:
                role_disp = "👤 USER" if turn["role"] == "user" else "🤖 MODEL"
                turn_str = f"### {role_disp}\n"
                if turn.get("clean_text"):
                    turn_str += turn["clean_text"] + "\n"

                if turn.get("formatted_media"):
                    turn_str += "\n" + "\n\n".join(turn["formatted_media"]) + "\n"

                if turn_str.strip():
                    master_blocks.append(turn_str.strip())

            chat_name = os.path.basename(chat_folder_path)

            master_md_lines = [
                "---",
                f'ai_service: "{master_service_name}"',
                f'integrated_sources: {json.dumps(list(sub_sources.keys()), ensure_ascii=False)}',
                f'total_merged_turns: {len(master_blocks)}',
                f'true_start_time: "{master_start_time}"',
                f'true_end_time: "{master_end_time}"',
                "---",
                f"\n# 🌟 統合マスターログ: {chat_name}\n",
                f"> ⚓ AiReKnots 重ね合わせ自動統合（統合ソース数: {len(sub_sources)} / 総ターン: {len(master_blocks)}）\n"
            ]
            master_md_lines.extend(master_blocks)
            final_master_content = "\n\n".join(master_md_lines)

            return {
                "chat_title": chat_name,
                "service_name": master_service_name,
                "start_time": master_start_time,
                "end_time": master_end_time,
                "sources": list(sub_sources.keys()),
                "total_turns": len(master_blocks),
                "master_markdown": final_master_content
            }, None

        except Exception as e:
            return None, f"統合処理中に例外が発生しました: {e}"

    def export_master_cache(self, chat_folder_path):
        """全ソースから統合された raw_master.md を物理保存"""
        res, err = self.build_integrated_master(chat_folder_path, is_export_master=False)
        if err or not res: return False, err

        master_md_path = os.path.join(chat_folder_path, "raw_master.md")

        try:
            with open(master_md_path, "w", encoding="utf-8") as f:
                f.write(res["master_markdown"])

            return True, master_md_path
        except Exception as e:
            return False, str(e)

    def cleanse_raw_sources(self, chat_folder_path):
        """統合完了後の元ソース（importer, scraped等）を削除して軽量化"""
        sources = self.scan_chat_sources(chat_folder_path)
        master_raw = os.path.join(chat_folder_path, "raw_master.md")
        if not os.path.exists(master_raw):
            return False, "統合マスター(raw_master.md)が存在しないためクレンジングを中止しました。"

        deleted_cnt = 0
        for s_key, s_info in sources.items():
            if s_key == "master": continue
            f_path = s_info.get("folder_path")
            if f_path and os.path.exists(f_path):
                try:
                    shutil.rmtree(f_path)
                    deleted_cnt += 1
                except: pass

        return True, f"{deleted_cnt} 個の元ソースフォルダを削除しました。"


# ================= 📊 ログ構造診断ビジュアライザー =================
class AiReKnotsVisualizerDialog(tk.Toplevel):
    def __init__(self, parent, engine, save_dir):
        super().__init__(parent)
        self.title("📊 AiReKnots - ログ構造診断ビジュアライザー")
        self.geometry("820x600")

        if os.path.exists(ICON_KNOTS):
            try: self.iconbitmap(ICON_KNOTS)
            except: pass

        self.engine = engine
        self.save_dir = save_dir
        self.current_view_mode = "table"

        self.build_ui()
        self.refresh_visualization()

    def build_ui(self):
        abs_path = os.path.abspath(self.save_dir)
        path_f = ttk.Frame(self, padding=5)
        path_f.pack(fill="x", side="top")
        ttk.Label(path_f, text=f"現在参照中のログ絶対パス:  [{abs_path}]", font=("MS Gothic", 9, "bold"), foreground="#2980b9").pack(anchor="w")

        mode_f = ttk.Frame(self, padding=5)
        mode_f.pack(fill="x", side="top")

        self.mode_var = tk.StringVar(value="table")
        ttk.Radiobutton(mode_f, text="📊 高密度スリムテーブル一覧モード", variable=self.mode_var, value="table", command=self.on_mode_changed).pack(side="left", padx=10)
        ttk.Radiobutton(mode_f, text="🌲 罫線ツリー階層構造モード", variable=self.mode_var, value="tree", command=self.on_mode_changed).pack(side="left", padx=10)

        self.container = ttk.Frame(self, padding=5)
        self.container.pack(fill="both", expand=True)

        self.tree_frame = ttk.Frame(self.container)
        self.table = ttk.Treeview(self.tree_frame, columns=("Master", "Importer", "Scraped", "Third"), show="tree headings")
        self.table.heading("#0", text="AIサービス / チャット題名")
        self.table.heading("Master", text="統合マスター(master)")
        self.table.heading("Importer", text="一括(importer)")
        self.table.heading("Scraped", text="サーバー(scraped)")
        self.table.heading("Third", text="第3ソース(3rd)")

        self.table.column("#0", width=280, anchor="w")
        self.table.column("Master", width=120, anchor="center")
        self.table.column("Importer", width=110, anchor="center")
        self.table.column("Scraped", width=110, anchor="center")
        self.table.column("Third", width=100, anchor="center")

        sb_tbl = ttk.Scrollbar(self.tree_frame, command=self.table.yview)
        self.table.configure(yscrollcommand=sb_tbl.set)
        self.table.pack(side="left", fill="both", expand=True)
        sb_tbl.pack(side="right", fill="y")

        self.text_frame = ttk.Frame(self.container)
        self.txt_tree = tk.Text(self.text_frame, background="#1e1e1e", foreground="#a0db86", font=("MS Gothic", 9), wrap="none")
        sb_txt_y = ttk.Scrollbar(self.text_frame, command=self.txt_tree.yview)
        sb_txt_x = ttk.Scrollbar(self.text_frame, orient="horizontal", command=self.txt_tree.xview)
        self.txt_tree.configure(yscrollcommand=sb_txt_y.set, xscrollcommand=sb_txt_x.set)

        self.txt_tree.grid(row=0, column=0, sticky="nsew")
        sb_txt_y.grid(row=0, column=1, sticky="ns")
        sb_txt_x.grid(row=1, column=0, sticky="ew")
        self.text_frame.rowconfigure(0, weight=1)
        self.text_frame.columnconfigure(0, weight=1)

    def on_mode_changed(self):
        self.current_view_mode = self.mode_var.get()
        self.refresh_visualization()

    def refresh_visualization(self):
        self.tree_frame.pack_forget()
        self.text_frame.pack_forget()

        if self.current_view_mode == "table":
            self.tree_frame.pack(fill="both", expand=True)
            self.render_table_view()
        else:
            self.text_frame.pack(fill="both", expand=True)
            self.render_tree_ascii_view()

    def render_table_view(self):
        self.table.delete(*self.table.get_children())
        if not os.path.exists(self.save_dir): return

        for ai_folder in os.listdir(self.save_dir):
            ai_path = os.path.join(self.save_dir, ai_folder)
            if os.path.isdir(ai_path) and ai_folder not in ["my_documents", "my_forge"]:
                parent_node = self.table.insert("", "end", text=f"📁 {ai_folder}", open=True)
                for chat in os.listdir(ai_path):
                    chat_path = os.path.join(ai_path, chat)
                    if os.path.isdir(chat_path):
                        sig = self.engine.get_chat_signal_data(chat_path)
                        srcs = sig["sources"]

                        def fmt(src_key):
                            d = srcs.get(src_key, {})
                            if d.get("has_md"):
                                return f"◯ ({d.get('asset_count', 0)}個)"
                            return f"× (0個)"

                        self.table.insert(
                            parent_node, "end",
                            text=f"💬 {chat}",
                            values=(fmt("master"), fmt("importer"), fmt("scraped"), fmt("3rd"))
                        )

    def render_tree_ascii_view(self):
        self.txt_tree.config(state="normal")
        self.txt_tree.delete("1.0", tk.END)

        abs_path = os.path.abspath(self.save_dir)
        lines = [f"📂 logs/ ({abs_path})\n"]

        if os.path.exists(self.save_dir):
            ai_folders = [f for f in os.listdir(self.save_dir) if os.path.isdir(os.path.join(self.save_dir, f)) and f not in ["my_documents", "my_forge"]]
            for idx, ai in enumerate(ai_folders):
                is_last_ai = (idx == len(ai_folders) - 1)
                prefix_ai = "└─ " if is_last_ai else "├─ "
                lines.append(f"{prefix_ai}📁 {ai}/")

                ai_path = os.path.join(self.save_dir, ai)
                chats = [c for c in os.listdir(ai_path) if os.path.isdir(os.path.join(ai_path, c))]
                child_prefix_ai = "    " if is_last_ai else "│   "

                for c_idx, chat in enumerate(chats):
                    is_last_chat = (c_idx == len(chats) - 1)
                    prefix_chat = "└─ " if is_last_chat else "├─ "
                    lines.append(f"{child_prefix_ai}{prefix_chat}💬 {chat}")

                    chat_path = os.path.join(ai_path, chat)
                    sig = self.engine.get_chat_signal_data(chat_path)
                    srcs = sig["sources"]

                    child_prefix_chat = child_prefix_ai + ("    " if is_last_chat else "│   ")
                    s_keys = ["master", "importer", "scraped", "3rd"]
                    for sk_idx, sk in enumerate(s_keys):
                        is_last_sk = (sk_idx == len(s_keys) - 1)
                        p_sk = "└─ " if is_last_sk else "├─ "
                        d = srcs.get(sk, {})
                        md_mark = "◯" if d.get("has_md") else "×"
                        cnt = d.get("asset_count", 0)
                        lines.append(f"{child_prefix_chat}{p_sk}[{sk}] (MD: {md_mark} / Assets: {cnt}個)")

        self.txt_tree.insert(tk.END, "\n".join(lines))
        self.txt_tree.config(state="disabled")


# ================= 🖥️ 単体起動時コントロールGUI =================
class AiReKnotsUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("⚓ AiReKnots - 重ね合わせ自動統合 ＆ 構造診断コア")
        self.geometry("680x560")

        if os.path.exists(ICON_KNOTS):
            try: self.iconbitmap(ICON_KNOTS)
            except: pass

        self.config_data = load_config()
        self.engine = AiReKnotsEngine(self.config_data)

        self.build_ui()

    def build_ui(self):
        ttk.Label(self, text="⚓ AiReKnots - ログ自動統合 ＆ 診断制御ハブ", font=("MS Gothic", 11, "bold")).pack(pady=6)

        p_frame = ttk.LabelFrame(self, text=" 🌟 統合マスターの優先順位（正当性）ルール ", padding=8)
        p_frame.pack(fill="x", padx=12, pady=4)

        self.priority_var = tk.StringVar(value=self.config_data.get("knots_priority_mode", "timespan_first"))

        r0 = ttk.Radiobutton(p_frame, text="⏳ 会話期間（true_start_time 〜 end_timeの時間の開き）が最も長いソースを最優先（推奨）", variable=self.priority_var, value="timespan_first", command=self.save_priority)
        r0.pack(anchor="w", pady=1)

        r1 = ttk.Radiobutton(p_frame, text="会話量・ファイル容量が最も多いソースを優先", variable=self.priority_var, value="most_info", command=self.save_priority)
        r1.pack(anchor="w", pady=1)

        r2 = ttk.Radiobutton(p_frame, text="最終更新日時が一番新しいソースを優先", variable=self.priority_var, value="latest", command=self.save_priority)
        r2.pack(anchor="w", pady=1)

        r3 = ttk.Radiobutton(p_frame, text="一括インポート (importer) のデータを優先", variable=self.priority_var, value="importer_first", command=self.save_priority)
        r3.pack(anchor="w", pady=1)

        act_f = ttk.LabelFrame(self, text=" 📊 診断 ＆ 一括処理アクション ", padding=8)
        act_f.pack(fill="x", padx=12, pady=4)

        btn_box_top = ttk.Frame(act_f)
        btn_box_top.pack(fill="x", pady=2)

        btn_diag = ttk.Button(btn_box_top, text="🔍 診断スキャン (ログコンソール出力)", command=self.run_scan_diagnosis)
        btn_diag.pack(side="left", fill="x", expand=True, padx=2)

        btn_v = ttk.Button(btn_box_top, text="📊 構造診断ビジュアライザーを開く", command=self.open_visualizer)
        btn_v.pack(side="right", fill="x", expand=True, padx=2)

        lock_f = ttk.Frame(act_f)
        lock_f.pack(fill="x", pady=4)

        self.var_lock_unlocked = tk.BooleanVar(value=False)
        chk_lock = ttk.Checkbutton(lock_f, text="🔒 一括生成・クレンジング処理の安全ロックを解除する", variable=self.var_lock_unlocked, command=self.toggle_action_buttons)
        chk_lock.pack(side="left")

        btn_box = ttk.Frame(act_f)
        btn_box.pack(fill="x", pady=2)

        self.btn_export = ttk.Button(btn_box, text="⚡ 全統合マスター・アセットを一括生成 (raw_master.md)", command=self.run_cache_export_all, state="disabled")
        self.btn_export.pack(side="left", fill="x", expand=True, padx=2)

        self.btn_cleanse = ttk.Button(btn_box, text="🧹 統合完了後に元ソースデータをクレンジング削除", command=self.run_cleansing_all, state="disabled")
        self.btn_cleanse.pack(side="right", fill="x", expand=True, padx=2)

        log_lf = ttk.LabelFrame(self, text=" 📜 実行ログコンソール ", padding=8)
        log_lf.pack(fill="both", expand=True, padx=12, pady=6)

        self.txt_log = tk.Text(log_lf, background="#1e1e1e", foreground="#a0db86", font=("MS Gothic", 9))
        self.txt_log.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(log_lf, command=self.txt_log.yview)
        sb.pack(side="right", fill="y")
        self.txt_log.configure(yscrollcommand=sb.set)

        self.log("💡 AiReKnots 統合エンジンが正常待機中です。")

    def log(self, msg):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"[{now}] {msg}\n")
        self.txt_log.see(tk.END)

    def save_priority(self):
        mode = self.priority_var.get()
        self.config_data["knots_priority_mode"] = mode
        save_config(self.config_data)
        self.engine.config = self.config_data
        self.log(f"⚙️ 優先順位ルールを 【{mode}】 に変更・保存しました。")

    def toggle_action_buttons(self):
        state_str = "normal" if self.var_lock_unlocked.get() else "disabled"
        self.btn_export.config(state=state_str)
        self.btn_cleanse.config(state=state_str)
        if self.var_lock_unlocked.get():
            self.log("🔓 安全ロックを解除しました。一括生成・クレンジング処理が可能です。")
        else:
            self.log("🔒 安全ロックを有効化しました。一括処理ボタンを保護しました。")

    def open_visualizer(self):
        save_dir = self.config_data.get("save_dir", os.path.join(CURRENT_DIR, "logs"))
        AiReKnotsVisualizerDialog(self, self.engine, save_dir)

    def run_scan_diagnosis(self):
        save_dir = self.config_data.get("save_dir", os.path.join(CURRENT_DIR, "logs"))
        if not os.path.exists(save_dir):
            self.log("❌ ログフォルダが存在しません。")
            return

        self.log("🔍 全チャットフォルダのソース構造診断を開始します...")
        total_chats = 0
        multi_source_chats = 0

        for ai_folder in os.listdir(save_dir):
            ai_path = os.path.join(save_dir, ai_folder)
            if os.path.isdir(ai_path) and ai_folder not in ["my_documents", "my_forge"]:
                for chat in os.listdir(ai_path):
                    chat_path = os.path.join(ai_path, chat)
                    if os.path.isdir(chat_path):
                        total_chats += 1
                        sig = self.engine.get_chat_signal_data(chat_path)
                        srcs = sig["sources"]
                        active_srcs = [k for k, v in srcs.items() if v.get("has_md")]
                        if len(active_srcs) > 1:
                            multi_source_chats += 1
                            self.log(f"  └─ 🔗 複数ソース検出: 『{chat}』 ➔ 保持ソース: {active_srcs}")

        self.log(f"🎉 スキャン完了: 全チャット {total_chats} 件中、複数ソース保持チャットは {multi_source_chats} 件でした。")

    def run_cache_export_all(self):
        save_dir = self.config_data.get("save_dir", os.path.join(CURRENT_DIR, "logs"))
        if not os.path.exists(save_dir): return

        ans = messagebox.askyesno("確認", "全チャットログの重ね合わせ統合と、 master/assets/ へのアセット集約一括生成を開始しますか？")
        if not ans: return

        self.log("⚡ 全チャットの統合マスター・アセット一括生成を開始します...")
        cnt = 0
        for ai in os.listdir(save_dir):
            ai_p = os.path.join(save_dir, ai)
            if os.path.isdir(ai_p) and ai not in ["my_documents", "my_forge"]:
                for chat in os.listdir(ai_p):
                    chat_p = os.path.join(ai_p, chat)
                    if os.path.isdir(chat_p):
                        ok, path_or_err = self.engine.export_master_cache(chat_p)
                        if ok: cnt += 1

        self.log(f"🎉 完了: 【{cnt} 件】 のチャットに統合マスター (raw_master.md) および master/assets/ を一括作成しました！")
        messagebox.showinfo("完了", f"{cnt} 件の統合マスターキャッシュを生成しました。")

    def run_cleansing_all(self):
        save_dir = self.config_data.get("save_dir", os.path.join(CURRENT_DIR, "logs"))
        if not os.path.exists(save_dir): return

        ans = messagebox.askyesno("⚠️ 最終削除確認", "統合マスター(raw_master.md)が生成済みのチャットにおいて、元データ(importer/scraped)を削除して容量を節約しますか？")
        if not ans: return

        self.log("🧹 元ソースデータのクレンジング一括処理を開始します...")
        cnt = 0
        for ai in os.listdir(save_dir):
            ai_p = os.path.join(save_dir, ai)
            if os.path.isdir(ai_p) and ai not in ["my_documents", "my_forge"]:
                for chat in os.listdir(ai_p):
                    chat_p = os.path.join(ai_p, chat)
                    if os.path.isdir(chat_p):
                        ok, msg = self.engine.cleanse_raw_sources(chat_p)
                        if ok: cnt += 1

        self.log(f"🎉 クレンジング完了: 【{cnt} 件】 のチャットから不要な元ソースデータを削除しました！")
        messagebox.showinfo("クレンジング完了", f"{cnt} 件のチャットの元ソースフォルダを削除・軽量化しました。")


if __name__ == '__main__':
    app = AiReKnotsUI()
    app.mainloop()