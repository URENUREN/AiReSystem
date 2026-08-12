# -*- coding: utf-8 -*-
# AiReCleat.pyw - Context Reconciliation Manager (0バイト回避＆バックアップ自動復元完全版)
import os
import sys
import json
import datetime
import re
import base64
import socket
import hashlib
import time
import threading
import subprocess
import atexit
import urllib.request
import urllib.error
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import shutil

# Windows特有のAppID登録
try:
    myappid = 'airelinker.suite.cleat.v26'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

# 🌟 100%動的絶対パス設定 (config.jsonの場所を絶対にブレさせない)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
ICON_CLEAT = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReCleat.ico"))
CONFIG_PATH = os.path.normpath(os.path.join(CURRENT_DIR, "config.json"))


# 🌟 0バイト自動回避 ＆ バックアップ自動復元機能付き設定読み込み
def load_config():
    cfg = {}
    config_bak_path = CONFIG_PATH + ".bak"

    # 1. 0バイト(空ファイル)回避 ＆ 読み込みリトライ (最大5回)
    for attempt in range(5):
        if os.path.exists(CONFIG_PATH) and os.path.getsize(CONFIG_PATH) > 0:
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if cfg and isinstance(cfg, dict):
                    return cfg
            except Exception:
                time.sleep(0.05)
        else:
            time.sleep(0.05)

    # 2. 万が一の読み込み失敗時 ➔ バックアップ (.bak) から自動復元
    if os.path.exists(config_bak_path) and os.path.getsize(config_bak_path) > 0:
        try:
            with open(config_bak_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            log_info("🔄 [自動復元] config.json の一時不整合を検知したため、バックアップ (.bak) から設定を復元しました。")
            return cfg
        except: pass

    log_info("⚠️ [警告] 設定ファイルが見つからないため、初期デフォルト値を適用します。")
    return {"sync_mode": "notify_portal", "keep_raw_payload": False, "stop_markdown_rewrite": False}


# 🌟 アトミック保存 ＆ 自動バックアップ生成
def save_config(cfg):
    tmp_path = CONFIG_PATH + ".tmp"
    bak_path = CONFIG_PATH + ".bak"
    try:
        # バックアップの更新保存
        if os.path.exists(CONFIG_PATH) and os.path.getsize(CONFIG_PATH) > 0:
            try: shutil.copy2(CONFIG_PATH, bak_path)
            except: pass

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        
        os.replace(tmp_path, CONFIG_PATH) # アトミック即時置換
    except Exception as e:
        log_info(f"⚠️ [警告] config.json の保存に失敗しました ({e})")
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass


# 🌟 config.json からリアルタイムに最新の保存先ディレクトリを取得
def get_current_save_dir():
    cfg = load_config()
    s_dir = cfg.get("save_dir", "")
    if s_dir and os.path.exists(s_dir):
        return os.path.normpath(s_dir)
    return os.path.join(CURRENT_DIR, "logs")


CLEAT_RUN_LOG_PATH = os.path.normpath(os.path.join(get_current_save_dir(), "cleat_run.log"))


def cleanup_log_file():
    if os.path.exists(CLEAT_RUN_LOG_PATH):
        try: os.remove(CLEAT_RUN_LOG_PATH)
        except: pass

atexit.register(cleanup_log_file)

standalone_app = None # スタンドアロンUIフック

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ================= 🛠 補助関数 ＆ クレンジング =================
def normalize_service_name(input_str_or_url):
    if not input_str_or_url: return "Google AI Studio"
    cfg = load_config()
    mappings = cfg.get("service_mappings", [])
    lower_input = str(input_str_or_url).lower().strip()

    for item in mappings:
        canonical = item.get("canonical_name", "その他AIサービス")
        keywords = item.get("keywords", [])
        for kw in keywords:
            if kw.lower() in lower_input: return canonical

    # 🌟 AI Overviews (検索AI) の判定を追加
    if "overview" in lower_input or "ai 概要" in lower_input or "検索ai" in lower_input:
        return "AI Overviews"
    elif "aistudio" in lower_input or "google ai studio" in lower_input: return "Google AI Studio"
    elif "gemini" in lower_input: return "Gemini"
    elif "chatgpt" in lower_input or "openai" in lower_input: return "ChatGPT"
    elif "claude" in lower_input or "anthropic" in lower_input: return "Claude"
    elif "perplexity" in lower_input: return "Perplexity"
    elif "notebooklm" in lower_input: return "NotebookLM"

    clean_name = re.sub(r'[\\/*?:"<>|]', "_", str(input_str_or_url)).strip()
    return clean_name if clean_name else "Google AI Studio"


def clean_scraped_ui_noise(text):
    if not text: return ""
    cleaned = re.sub(r'^(?:User|Model)\s+\d{1,2}:\d{2}\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^\s*(?:Thoughts|Expand to view model thoughts|chevron_right|image|Preview unavailable|downloadfullscreen|progress_activity|docs|play_circle)\s*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'<thought>[\s\S]*?</thought>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def get_file_md5(filepath):
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        log_info(f"⚠️ [ハッシュ計算失敗] {os.path.basename(filepath)} ({e})")
        return None


def detect_file_type(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"): return "png", "image/png"
    elif data.startswith(b"\xff\xd8"): return "jpg", "image/jpeg"
    elif data.startswith(b"GIF8"): return "gif", "image/gif"
    elif data.startswith(b"RIFF") and b"WEBP" in data[8:12]: return "webp", "image/webp"
    elif data.startswith(b"BM"): return "bmp", "image/bmp"
    elif data.startswith(b"ID3") or data.startswith(b"\xff\xfb") or data.startswith(b"\xff\xf3") or data.startswith(b"\xff\xf2"): return "mp3", "audio/mp3"
    elif data.startswith(b"RIFF") and b"WAVE" in data[8:12]: return "wav", "audio/wav"
    elif b"ftyp" in data[4:16]: return "mp4", "video/mp4"
    elif data.startswith(b"OggS"): return "ogg", "audio/ogg"
    elif data.startswith(b"PK\x03\x04"): return "zip", "application/zip"
    elif data.startswith(b"%PDF"): return "pdf", "application/pdf"
    return None, None


def format_iso_to_plain(iso_str):
    if not iso_str: return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        clean = re.sub(r'\.\d+Z$', '', iso_str).replace('T', ' ').replace('Z', '')
        utc_dt = datetime.datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        jst_dt = utc_dt + datetime.timedelta(hours=9)
        return jst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except: return iso_str


def log_info(message):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{now}] {message}"
    save_dir = get_current_save_dir()
    log_path = os.path.normpath(os.path.join(save_dir, "cleat_run.log"))
    try:
        os.makedirs(save_dir, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(formatted_msg + "\n")
    except: pass

    if standalone_app:
        standalone_app.root.after(0, lambda: standalone_app.log_direct(message))

    try:
        url = "http://127.0.0.1:5000/cleat_log"
        data = json.dumps({"message": message}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=1) as res: pass
    except: pass


# 🌟 ファイル削除失敗時も理由を隠さずログ出力するリトライ付き削除関数
def safe_remove_file(filepath):
    if not os.path.exists(filepath): return True
    for attempt in range(3):
        try:
            os.remove(filepath)
            return True
        except Exception as e:
            if attempt == 2:
                log_info(f"⚠️ [ファイル削除失敗] {os.path.basename(filepath)} の削除に失敗しました ({e})")
            time.sleep(0.1)
    return False


def safe_remove_dir(dirpath):
    if not os.path.exists(dirpath): return True
    for attempt in range(3):
        try:
            shutil.rmtree(dirpath)
            return True
        except Exception as e:
            if attempt == 2:
                log_info(f"⚠️ [フォルダ削除失敗] {os.path.basename(dirpath)} の削除に失敗しました ({e})")
            time.sleep(0.1)
    return False


# 🌟 設定に応じて raw_payload.json を一次変換直後に自動削除クレンジング
def cleanup_payload_only_if_needed(chat_folder):
    cfg = load_config()
    keep_payload = cfg.get("keep_raw_payload", False)
    if not keep_payload:
        payload_p = os.path.join(chat_folder, "scraped", "raw_payload.json")
        if os.path.exists(payload_p):
            if safe_remove_file(payload_p):
                log_info("🧹 [クレンジング] 一時データ raw_payload.json を自動削除しました。")


# 🌟 一時ファイル群の全自動リトライ付きクレンジング関数
def cleanup_all_temp_files(chat_folder, keep_incoming=False):
    scraped_folder = os.path.join(chat_folder, "scraped")
    cleanup_payload_only_if_needed(chat_folder)

    # プレビュー用一時ファイル・フォルダーの完全クレンジング
    prev_md = os.path.join(scraped_folder, "raw_merged_preview.md")
    prev_assets = os.path.join(scraped_folder, "merged_preview_assets")
    safe_remove_file(prev_md)
    safe_remove_dir(prev_assets)

    # raw_incoming.md と incoming_assets/ のクレンジング (keep_incoming=False の場合)
    if not keep_incoming:
        inc_md = os.path.join(scraped_folder, "raw_incoming.md")
        inc_assets = os.path.join(scraped_folder, "incoming_assets")
        safe_remove_file(inc_md)
        safe_remove_dir(inc_assets)


# 🌟 本物のアライメントマージエンジン (AiReLinkage.pyw) のバトン渡しキック呼出し
def call_linkage_engine(chat_folder_path, mode="auto_merge"):
    linkage_script = os.path.join(CURRENT_DIR, "AiReLinkage.pyw")
    if os.path.exists(linkage_script):
        try:
            log_info(f"🔀 AiReLinkage.pyw 外部エンジンを起動バトンタッチします... (モード: {mode})")
            subprocess.Popen([sys.executable, linkage_script, "--chat-folder", chat_folder_path, "--mode", mode])
            return True
        except Exception as e:
            log_info(f"❌ AiReLinkage 起動エラー: {e}")
            return False
    else:
        log_info(f"❌ エラー: AiReLinkage.pyw が見つかりません: {linkage_script}")
        return False


# ================= 🌟 1回目保存専用 (JSON ➔ 直接 raw_scraped.md ＆ assets/) =================
def convert_json_to_direct_master(chat_folder_path):
    scraped_folder = os.path.join(chat_folder_path, "scraped")
    payload_path = os.path.join(scraped_folder, "raw_payload.json")

    if not os.path.exists(payload_path):
        return False, f"raw_payload.json が見つかりません: {payload_path}"

    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"JSON展開エラー: {e}"

    conversations = data.get("conversations", [])
    thread_id = os.path.basename(chat_folder_path)
    ai_folder_name = data.get("ai_service", "Google AI Studio")
    url_str = data.get("url", "")
    true_start = format_iso_to_plain(data.get('true_start_time', ''))
    true_end = format_iso_to_plain(data.get('true_end_time', ''))

    # 🌟 本番用 assets/ フォルダに直接保存
    assets_dir = os.path.join(scraped_folder, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    md_lines = [
        "---",
        f'ai_service: "{ai_folder_name}"',
        'mark: "☆ 無し"',
        'tags: ["ブラウザ保存"]',
        f'true_start_time: "{true_start}"',
        f'true_end_time: "{true_end}"',
        "---",
        f"\n# [■] 生ログ: {thread_id}\n",
        f"- URL: {url_str}\n",
        f"- 開始: {true_start}\n",
        f"- 終了: {true_end}\n\n"
    ]

    asset_counter = 1
    for turn in conversations:
        role = turn.get("role", "unknown")
        disp_role = "👤 USER" if role == "user" else "🤖 MODEL"
        parts = turn.get("parts", [])
        turn_text = ""
        bound_links = []
        
        for part in parts:
            if not isinstance(part, dict): continue
            if "text" in part and part["text"]:
                turn_text += str(part["text"]) + "\n"
                
            inline = part.get("inlineData") or part.get("inline_data") or part.get("inlineImage") or part.get("inline_image")
            if inline and isinstance(inline, dict):
                b64_data = inline.get("data", "")
                if b64_data:
                    if "," in b64_data: b64_data = b64_data.split(",")[1]
                    try:
                        decoded_data = base64.b64decode(b64_data)
                        ext, _ = detect_file_type(decoded_data)
                        if not ext: ext = "png"
                        
                        asset_filename = f"asset_{asset_counter}.{ext}"
                        with open(os.path.join(assets_dir, asset_filename), "wb") as img_f:
                            img_f.write(decoded_data)
                        
                        if ext in ["png", "jpg", "jpeg", "gif", "webp", "bmp"]:
                            bound_links.append(f"\n![添付メディア](./assets/{asset_filename})\n")
                        elif ext in ["mp3", "wav", "ogg"]:
                            bound_links.append(f"\n<audio src=\"./assets/{asset_filename}\" controls></audio>\n")
                        elif ext in ["mp4"]:
                            bound_links.append(f"\n<video src=\"./assets/{asset_filename}\" controls width=\"420\"></video>\n")
                        else:
                            bound_links.append(f"\n[📎 添付ファイル: {asset_filename}](./assets/{asset_filename})\n")
                        
                        asset_counter += 1
                    except Exception as e:
                        log_info(f"⚠️ アセット復元失敗: {e}")

        clean_txt = clean_scraped_ui_noise(turn_text)
        body_content = clean_txt.strip()
        if bound_links:
            body_content += "\n" + "\n".join(bound_links)

        if body_content.strip():
            md_lines.append(f"### {disp_role}\n{body_content}\n")

    output_master_md_path = os.path.join(scraped_folder, "raw_scraped.md")
    with open(output_master_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return True, output_master_md_path


# ================= 🌟 2回目以降用: 一次変換 (JSON ➔ raw_incoming.md ＆ incoming_assets/) =================
def convert_json_to_incoming_md(chat_folder_path):
    scraped_folder = os.path.join(chat_folder_path, "scraped")
    payload_path = os.path.join(scraped_folder, "raw_payload.json")

    if not os.path.exists(payload_path):
        return False, f"raw_payload.json が見つかりません: {payload_path}"

    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"JSON展開エラー: {e}"

    conversations = data.get("conversations", [])
    thread_id = os.path.basename(chat_folder_path)
    ai_folder_name = data.get("ai_service", "Google AI Studio")
    url_str = data.get("url", "")
    true_start = format_iso_to_plain(data.get('true_start_time', ''))
    true_end = format_iso_to_plain(data.get('true_end_time', ''))

    incoming_assets_dir = os.path.join(scraped_folder, "incoming_assets")
    safe_remove_dir(incoming_assets_dir)
    os.makedirs(incoming_assets_dir, exist_ok=True)

    md_lines = [
        "---",
        f'ai_service: "{ai_folder_name}"',
        'mark: "☆ 無し"',
        'tags: ["ブラウザ保存"]',
        f'true_start_time: "{true_start}"',
        f'true_end_time: "{true_end}"',
        "---",
        f"\n# [■] 生ログ: {thread_id}\n",
        f"- URL: {url_str}\n",
        f"- 開始: {true_start}\n",
        f"- 終了: {true_end}\n\n"
    ]

    asset_counter = 1
    for turn in conversations:
        role = turn.get("role", "unknown")
        disp_role = "👤 USER" if role == "user" else "🤖 MODEL"
        parts = turn.get("parts", [])
        turn_text = ""
        bound_links = []
        
        for part in parts:
            if not isinstance(part, dict): continue
            if "text" in part and part["text"]:
                turn_text += str(part["text"]) + "\n"
                
            inline = part.get("inlineData") or part.get("inline_data") or part.get("inlineImage") or part.get("inline_image")
            if inline and isinstance(inline, dict):
                b64_data = inline.get("data", "")
                if b64_data:
                    if "," in b64_data: b64_data = b64_data.split(",")[1]
                    try:
                        decoded_data = base64.b64decode(b64_data)
                        ext, _ = detect_file_type(decoded_data)
                        if not ext: ext = "png"
                        
                        asset_filename = f"inc_asset_{asset_counter}.{ext}"
                        with open(os.path.join(incoming_assets_dir, asset_filename), "wb") as img_f:
                            img_f.write(decoded_data)
                        
                        if ext in ["png", "jpg", "jpeg", "gif", "webp", "bmp"]:
                            bound_links.append(f"\n![添付メディア](./incoming_assets/{asset_filename})\n")
                        elif ext in ["mp3", "wav", "ogg"]:
                            bound_links.append(f"\n<audio src=\"./incoming_assets/{asset_filename}\" controls></audio>\n")
                        elif ext in ["mp4"]:
                            bound_links.append(f"\n<video src=\"./incoming_assets/{asset_filename}\" controls width=\"420\"></video>\n")
                        else:
                            bound_links.append(f"\n[📎 添付ファイル: {asset_filename}](./incoming_assets/{asset_filename})\n")
                        
                        asset_counter += 1
                    except Exception as e:
                        log_info(f"⚠️ アセット復元失敗: {e}")

        clean_txt = clean_scraped_ui_noise(turn_text)
        body_content = clean_txt.strip()
        if bound_links:
            body_content += "\n" + "\n".join(bound_links)

        if body_content.strip():
            md_lines.append(f"### {disp_role}\n{body_content}\n")

    output_incoming_md_path = os.path.join(scraped_folder, "raw_incoming.md")
    with open(output_incoming_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return True, output_incoming_md_path


# ================= 🌟 全自動バックグラウンド処理 (process_background_sync) =================
def process_background_sync(chat_folder, sync_mode="full", detailed_log=True):
    scraped_folder = os.path.join(chat_folder, "scraped")
    assets_folder_path = os.path.join(scraped_folder, "assets")
    payload_path = os.path.join(scraped_folder, "raw_payload.json")
    raw_filepath = os.path.join(scraped_folder, "raw_scraped.md")

    if not os.path.exists(payload_path):
        log_info("❌ エラー: raw_payload.json が見つかりません。")
        return

    # 🌟 1. 初回保存判定 (raw_scraped.md または scraped/ 自体が存在しない場合 ➔ 直接本番保存)
    if not os.path.exists(raw_filepath):
        log_info(f"🆕 [初回保存] raw_scraped.md が存在しないため、直接本番ログ・アセットとして保存します。")
        ok, msg = convert_json_to_direct_master(chat_folder)
        if ok:
            log_info(f"✨ [初回保存完了] raw_scraped.md ＆ assets/ を直接生成・確定保存しました。")
            cleanup_all_temp_files(chat_folder, keep_incoming=False)
        else:
            log_info(f"❌ [初回保存失敗] {msg}")
        return

    # 🌟 2. 2回目以降の同期時 ➔ 一時変換 (JSON ➔ raw_incoming.md ＆ incoming_assets/) の実行
    ok, msg = convert_json_to_incoming_md(chat_folder)
    if not ok:
        log_info(f"❌ 一次変換失敗: {msg}")
        return

    # 🌟 JSON 一時データ (raw_payload.json) は一次変換完了直後に削除クレンジング！
    cleanup_payload_only_if_needed(chat_folder)

    incoming_md_path = os.path.join(scraped_folder, "raw_incoming.md")
    incoming_assets_dir = os.path.join(scraped_folder, "incoming_assets")

    # 🌟 リアルタイムに絶対パスの config.json から同期モードをロード！
    cfg_data = load_config()
    stop_markdown_rewrite = cfg_data.get("stop_markdown_rewrite", False)
    current_sync_mode = cfg_data.get("sync_mode", "notify_portal") # デフォルト: モード4

    log_info(f"🔍 [動作モード確認] 現在適用されている設定モード: 【{current_sync_mode}】")

    if stop_markdown_rewrite:
        log_info("🛡️ [検証モード] Markdown書き換え停止中のため、raw_scraped.md の更新をスキップしました。")
        cleanup_all_temp_files(chat_folder, keep_incoming=False)
        return

    # 🌟 モード1: 全自動上書き (MD5ハッシュ重複排除 ＆ 古い assets/ 内全消去更地化)
    if current_sync_mode == "auto_overwrite":
        log_info("⚡ [モード1: 全自動上書き] raw_incoming.md で本番ログを上書き適用します。")
        
        # 1. 古い assets/ フォルダの中身を一度全消去クリア！
        safe_remove_dir(assets_folder_path)
        os.makedirs(assets_folder_path, exist_ok=True)

        # 2. incoming_assets/ のアセットを MD5 ハッシュ重複チェックしながら asset_1.ext 〜 へ保存
        file_to_hash = {}
        hash_to_final_fname = {}
        inc_counter = 1

        if os.path.exists(incoming_assets_dir):
            inc_files = sorted([f for f in os.listdir(incoming_assets_dir) if not f.endswith(".bin")], key=natural_sort_key)
            for f in inc_files:
                sp = os.path.join(incoming_assets_dir, f)
                if os.path.isfile(sp):
                    fh = get_file_md5(sp)
                    if fh:
                        if fh not in hash_to_final_fname:
                            ext = f.split(".")[-1].lower() if "." in f else "png"
                            final_fn = f"asset_{inc_counter}.{ext}"
                            hash_to_final_fname[fh] = final_fn
                            inc_counter += 1
                            shutil.copy2(sp, os.path.join(assets_folder_path, final_fn))
                        
                        file_to_hash[f] = hash_to_final_fname[fh]

        # 3. raw_incoming.md 内のアセット参照タグ（./incoming_assets/inc_asset_X.ext）を MD5 ハッシュ整合名に完全置換して raw_scraped.md に保存！
        if os.path.exists(incoming_md_path):
            with open(incoming_md_path, "r", encoding="utf-8") as f:
                inc_content = f.read()

            def replace_inc_asset_match(match):
                full_match = match.group(0)
                fname = os.path.basename(match.group(1))
                if fname in file_to_hash:
                    return full_match.replace(match.group(1), f"./assets/{file_to_hash[fname]}")
                return full_match.replace("./incoming_assets/inc_asset_", "./assets/asset_")

            scraped_content = re.sub(r'(\./incoming_assets/[^\s\)\>"\']+)', replace_inc_asset_match, inc_content)
            
            with open(raw_filepath, "w", encoding="utf-8") as f:
                f.write(scraped_content)

        cleanup_all_temp_files(chat_folder, keep_incoming=False)

    # 🌟 モード2: 全自動マージ ➔ AiReLinkage.pyw にバトンタッチして即終了！
    elif current_sync_mode == "auto_merge":
        log_info("✨ [モード2: 全自動マージ] AiReLinkage.pyw へ処理をバトンタックスします。")
        call_linkage_engine(chat_folder, mode="auto_merge")

    # 🌟 モード3: 即時確認ポップアップ ➔ AiReLinkage.pyw (選択画面) へバトンタッチして即終了！
    elif current_sync_mode == "prompt_popup":
        log_info("🔔 [モード3: 確認ダイアログ] AiReLinkage.pyw の選択画面へバトンタッチします。")
        call_linkage_engine(chat_folder, mode="prompt")

    # 🌟 モード4: 静的蓄積・ポータル通知 (新着を保持して待機終了)
    else:
        log_info("💬 [モード4: 静的蓄積] raw_incoming.md ＆ incoming_assets/ を保存し待機します。")


# ================= 🖥️ スタンドアロン GUI モード (UI美化・整列完成版) =================
class AiReCleatStandaloneUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🔨 AiReCleat - リアルタイムログ調停 ＆ 監視コンソール")
        self.root.geometry("750x580")
        self.root.resizable(True, True)

        global standalone_app
        standalone_app = self

        self.config = load_config()
        self.var_detailed_cleat = tk.BooleanVar(value=True)
        self.var_keep_payload = tk.BooleanVar(value=self.config.get("keep_raw_payload", False))
        self.var_stop_rewrite = tk.BooleanVar(value=self.config.get("stop_markdown_rewrite", False))
        self.var_sync_mode = tk.StringVar(value=self.config.get("sync_mode", "notify_portal"))
        self.cleat_log_history = []

        self.apply_window_icon()

        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="both", expand=True)

        top_f = ttk.Frame(frame)
        top_f.pack(fill="x", pady=(0, 10))

        title_lbl = ttk.Label(top_f, text="🔨 AiReCleat ログ差分調停 ＆ 監視コンソール", font=("MS PGothic", 11, "bold"))
        title_lbl.pack(side="left")

        btn_box_top = ttk.Frame(top_f)
        btn_box_top.pack(side="right")

        ttk.Button(btn_box_top, text="📡 Server表示", command=self.show_linker_server).pack(side="left", padx=2)
        ttk.Button(btn_box_top, text="🔀 LinkageViewer表示", command=self.show_linkage_viewer).pack(side="left", padx=2)

        # 🌟 モード1 ➔ 2 ➔ 3 ➔ 4 の順にピッタリ縦整列
        mode_lf = ttk.LabelFrame(frame, text=" ⚙️ 2回目以降の同期動作モード (config.json) ", padding=10)
        mode_lf.pack(fill="x", pady=2)

        m1 = ttk.Radiobutton(mode_lf, text="モード1: 全自動上書き（常に新着データで上書き）", variable=self.var_sync_mode, value="auto_overwrite", command=self.on_mode_radio_changed)
        m1.pack(anchor="w", pady=2)

        m2 = ttk.Radiobutton(mode_lf, text="モード2: 全自動相補マージ（裏で自動合体適用）", variable=self.var_sync_mode, value="auto_merge", command=self.on_mode_radio_changed)
        m2.pack(anchor="w", pady=2)

        m3 = ttk.Radiobutton(mode_lf, text="モード3: 即時確認ダイアログを表示（1クリック選択 ＆ ビューワー呼び出し）", variable=self.var_sync_mode, value="prompt_popup", command=self.on_mode_radio_changed)
        m3.pack(anchor="w", pady=2)

        m4 = ttk.Radiobutton(mode_lf, text="モード4: 静的蓄積（画面を出さず新着を保持、ポータル等で確認）", variable=self.var_sync_mode, value="notify_portal", command=self.on_mode_radio_changed)
        m4.pack(anchor="w", pady=2)

        log_lf = ttk.LabelFrame(frame, text=" 📝 差分判定・調停リアルタイムログ ", padding=8)
        log_lf.pack(fill="both", expand=True, pady=5)

        right_header_f = ttk.Frame(log_lf)
        right_header_f.pack(fill="x", side="top", pady=(0, 4))

        lbl_cleat = ttk.Label(right_header_f, text="📝 調停ログコンソール", font=("MS Gothic", 9, "bold"))
        lbl_cleat.pack(side="left", padx=5)

        self.chk_detailed_cleat = ttk.Checkbutton(right_header_f, text="詳細ログを表示", variable=self.var_detailed_cleat, command=self.refresh_cleat_logs)
        self.chk_detailed_cleat.pack(side="right", padx=5)

        # 🌟 絵文字・隙間・不自然な間を完全排除したクリーンテキスト
        self.chk_keep_payload = ttk.Checkbutton(right_header_f, text="一時データ(raw_payload.json)を残す", variable=self.var_keep_payload, command=self.on_toggle_options)
        self.chk_keep_payload.pack(side="right", padx=5)

        self.chk_stop_rewrite = ttk.Checkbutton(right_header_f, text="Markdown書き出し停止(検証)", variable=self.var_stop_rewrite, command=self.on_toggle_options)
        self.chk_stop_rewrite.pack(side="right", padx=5)

        right_content_f = ttk.Frame(log_lf)
        right_content_f.pack(fill="both", expand=True, side="top")

        self.log_text = tk.Text(right_content_f, background="#1e1e1e", fg="#a0db86", font=("MS Gothic", 9))
        self.log_text.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(right_content_f, command=self.log_text.yview)
        sb.pack(fill="y", side="right")
        self.log_text.config(yscrollcommand=sb.set)

        self.log("💡 AiReCleat リアルタイム調停コンソールが正常に待機・起動しました。")
        self.log(f"💡 現在の動作モード: 【{self.var_sync_mode.get()}】")

        self.poll_shared_log()

    def apply_window_icon(self):
        if os.path.exists(ICON_CLEAT):
            try:
                self.root.iconbitmap(default=ICON_CLEAT)
                img = Image.open(ICON_CLEAT)
                self._icon_photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self._icon_photo)
            except:
                try: self.root.iconbitmap(ICON_CLEAT)
                except: pass

    # 🌟 ファイル衝突に負けない安全なログ読み込み
    def poll_shared_log(self):
        save_dir = get_current_save_dir()
        log_path = os.path.normpath(os.path.join(save_dir, "cleat_run.log"))
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                    lines = lf.readlines()
                new_logged = False
                for line in lines:
                    clean_line = line.strip()
                    if clean_line and clean_line not in self.cleat_log_history:
                        self.cleat_log_history.append(clean_line)
                        new_logged = True
                if new_logged: self.refresh_cleat_logs()
            except Exception as e:
                log_info(f"⚠️ [ログ監視失敗] cleat_run.log 読み込みエラー ({e})")
        self.root.after(1000, self.poll_shared_log)

    def on_mode_radio_changed(self):
        mode = self.var_sync_mode.get()
        self.config["sync_mode"] = mode
        save_config(self.config)
        self.log(f"⚙️ 設定変更: 同期動作モードを 【{mode}】 に変更・保存しました。")

    def on_toggle_options(self):
        self.config["keep_raw_payload"] = self.var_keep_payload.get()
        self.config["stop_markdown_rewrite"] = self.var_stop_rewrite.get()
        save_config(self.config)
        status_payload = "保持" if self.var_keep_payload.get() else "自動削除"
        status_rewrite = "停止中(検証モード)" if self.var_stop_rewrite.get() else "通常稼働"
        self.log(f"⚙️ 設定変更: raw_payload={status_payload} | MD書き換え={status_rewrite}")

    def refresh_cleat_logs(self):
        detailed = self.var_detailed_cleat.get()
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        for msg in self.cleat_log_history:
            self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def show_linker_server(self):
        try:
            urllib.request.urlopen("http://127.0.0.1:5000/show", timeout=1)
            self.log("📡 常駐中継サーバー（AiReLinker）のウィンドウ呼び出し信号を送信しました。")
        except:
            self.log("❌ サーバー信号エラー: AiReLinkerServerが起動していません。")

    def show_linkage_viewer(self):
        viewer_script = os.path.join(CURRENT_DIR, "AiReLinkageViewer.pyw")
        if os.path.exists(viewer_script):
            args = [sys.executable, viewer_script]
            chat_folder = self.config.get("last_chat_folder")
            if chat_folder and os.path.exists(chat_folder):
                args.extend(["--chat-folder", chat_folder])
                
            subprocess.Popen(args)
            self.log("🔀 差分比較ビューワー (AiReLinkageViewer) を起動・呼び出しました。")
        else:
            self.log(f"❌ エラー: AiReLinkageViewer.pyw が見つかりません: {viewer_script}")

    def log_direct(self, message):
        if message not in self.cleat_log_history:
            self.cleat_log_history.append(message)
        self.refresh_cleat_logs()

    def log(self, message):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        formatted = f"[{now}] {message}"
        save_dir = get_current_save_dir()
        log_path = os.path.normpath(os.path.join(save_dir, "cleat_run.log"))
        try:
            os.makedirs(save_dir, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(formatted + "\n")
        except: pass
        if formatted not in self.cleat_log_history:
            self.cleat_log_history.append(formatted)
        self.refresh_cleat_logs()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        _cleat_mutex = None
        try:
            _cleat_mutex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _cleat_mutex.bind(('127.0.0.1', 5002))
        except OSError:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(('127.0.0.1', 5002))
                s.close()
            except: pass
            sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--chat-folder":
        chat_folder = sys.argv[2]
        process_background_sync(chat_folder)
    else:
        root = tk.Tk()
        app = AiReCleatStandaloneUI(root)
        
        def start_mutex_listener(app_ui):
            def run_listener():
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.bind(('127.0.0.1', 5002))
                    s.listen(1)
                    while True:
                        conn, addr = s.accept()
                        conn.close()
                        app_ui.root.after(0, lambda: app_ui.show_standalone_and_focus())
                except: pass
            threading.Thread(target=run_listener, daemon=True).start()
            
        def show_standalone_and_focus():
            app.root.deiconify()
            app.root.lift()
            app.root.focus_force()
            app.log("🔔 二重起動を検知したため、既存のウィンドウを前面に呼び出しました。")
            
        app.show_standalone_and_focus = show_standalone_and_focus
        
        if _cleat_mutex: _cleat_mutex.close() 
        start_mutex_listener(app)
        root.mainloop()