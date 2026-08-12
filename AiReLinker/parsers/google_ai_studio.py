# -*- coding: utf-8 -*-
# google_ai_studio.py - Google AI Studio 専用解析・パース・全ファイルアセット収集プラグイン (マルチスレッド並列スキャン爆速化版)
import os
import json
import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

def parse_utc_to_jst(utc_str):
    """UTCタイムスタンプを日本時間(JST)文字列に変換"""
    if not utc_str:
        return ""
    try:
        clean_time = re.sub(r'\.\d+Z$', '', utc_str).replace('T', ' ').replace('Z', '')
        utc_dt = datetime.datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
        jst_dt = utc_dt + datetime.timedelta(hours=9)
        return jst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return utc_str

def sanitize_filename(filename):
    """不吉な文字を除去した安全なファイル名を作成"""
    if not filename:
        return "Untitled_Chat"
    clean_name = re.sub(r'[\\/*?:"<>|]', "_", filename)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    return clean_name if clean_name else "Untitled_Chat"

def normalize_text(text):
    """テキストの改行や空白の正規化"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def detect_turn_role(turn, index, total_turns):
    """発言者（USER / MODEL）の厳格な判別補正関数"""
    raw_role = ""
    if isinstance(turn, dict):
        raw_role = str(turn.get("role", "")).lower().strip()

    if raw_role in ["user", "human", "prompt", "input"]:
        return "user"
    elif raw_role in ["model", "assistant", "bot", "output", "response"]:
        return "model"

    return "user" if index % 2 == 0 else "model"

def parse_google_ai_studio_chat(file_path, file_name, raw_data, declared_svc="自動判別", new_svc_name=""):
    """
    単一のログファイル（JSON）を解析し、タイトル、発言ターン、日時、AIサービス種別を判定します。
    """
    try:
        data = json.loads(raw_data)
    except:
        return None

    # 🌟 構造体優先の厳格なAIサービス判定ロジック！
    if declared_svc != "自動判別":
        service_name = new_svc_name if declared_svc == "新規追加..." else declared_svc
    else:
        file_lower = file_name.lower()
        
        # 1. 構造体キーを最優先でチェック（会話テキスト内の単語による誤判定を物理的に防ぐ！）
        if isinstance(data, dict) and ("chunkedPrompt" in data or "runSettings" in data or "systemInstruction" in data.get("prompt", {})):
            service_name = "Google AI Studio"
        elif "conversations.json" in file_lower or (isinstance(data, list) and len(data) > 0 and "mapping" in data[0]):
            service_name = "ChatGPT"
        elif "chat_messages" in file_name.lower():
            service_name = "Claude"
        elif "perplexity" in file_lower:
            service_name = "Perplexity"
        elif "notebook" in file_lower:
            service_name = "NotebookLM"
        elif "genspark" in file_lower:
            service_name = "Genspark"
        elif "gemini" in file_lower:
            service_name = "Gemini"
        elif isinstance(data, dict) and ("contents" in data or "prompt" in data):
            service_name = "Google AI Studio"
        else:
            # 2. どの特徴・構造にも当てはまらない場合のフォールバック表記！
            service_name = "未識別AI/その他"

    title = ""
    if isinstance(data, dict):
        title = data.get("title", data.get("name", ""))
    if not title:
        title = os.path.splitext(file_name)[0].strip()

    true_start_time_val = ""
    true_end_time_val = ""
    model_id_val = "gemini-1.5-flash"
    contents = []

    if isinstance(data, dict):
        if "runSettings" in data and isinstance(data["runSettings"], dict):
            model_id_val = data["runSettings"].get("model", "gemini-1.5-flash").replace("models/", "")

        if "chunkedPrompt" in data and isinstance(data["chunkedPrompt"], dict) and "chunks" in data["chunkedPrompt"]:
            chunks = data["chunkedPrompt"]["chunks"]
            if isinstance(chunks, list) and chunks:
                if "createTime" in chunks[0]:
                    true_start_time_val = parse_utc_to_jst(chunks[0]["createTime"])
                if "createTime" in chunks[-1]:
                    true_end_time_val = parse_utc_to_jst(chunks[-1]["createTime"])

                for c in chunks:
                    if isinstance(c, dict):
                        contents.append({
                            "parts": [{"text": c.get("text", "")}],
                            "role": "user" if c.get("role") in ["user", "human", "prompt"] else "model"
                        })

        elif "contents" in data and isinstance(data["contents"], list):
            contents = data["contents"]
        elif "prompt" in data and isinstance(data["prompt"], dict) and "contents" in data["prompt"]:
            contents = data["prompt"]["contents"]

    if not contents:
        return None

    if not true_end_time_val:
        try:
            mtime = os.path.getmtime(file_path)
            true_end_time_val = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except:
            true_end_time_val = "不明"
    if not true_start_time_val:
        true_start_time_val = true_end_time_val

    for idx, turn in enumerate(contents):
        if isinstance(turn, dict):
            turn["role"] = detect_turn_role(turn, idx, len(contents))

    system_instruction = ""
    if isinstance(data, dict) and "prompt" in data and isinstance(data["prompt"], dict):
        if "systemInstruction" in data["prompt"]:
            sys_ins = data["prompt"]["systemInstruction"]
            if isinstance(sys_ins, dict) and "parts" in sys_ins:
                system_instruction = "\n".join([p.get("text", "") for p in sys_ins["parts"] if isinstance(p, dict) and "text" in p])

    return {
        "file_name": file_name,
        "title": title,
        "service": service_name,
        "model_id": model_id_val,
        "start_time": true_start_time_val,
        "end_time": true_end_time_val,
        "raw_json_data": data,
        "raw_text_data": raw_data,
        "parsed_contents": contents,
        "system_instruction": system_instruction
    }

def _worker_read_and_parse(file_path, file_name, parse_mode, declared_svc, new_svc_name):
    """🌟 マルチスレッド用 1ファイルの読込 ＆ パースワーカー"""
    if parse_mode == "拡張子なしファイルのみ" and "." in file_name:
        return None, file_name
    elif parse_mode == "JSONファイルのみ (.json)" and not file_name.endswith(".json"):
        return None, file_name
    elif parse_mode == "Markdownファイルのみ (.md)" and not file_name.endswith(".md"):
        return None, file_name

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = f.read()
        parsed_chat = parse_google_ai_studio_chat(file_path, file_name, raw_data, declared_svc, new_svc_name)
        if parsed_chat and parsed_chat["parsed_contents"]:
            return parsed_chat, None
    except: pass
    return None, file_name

def scan_google_ai_studio_directory(src_dir, parse_mode="拡張子なしファイルのみ", declared_svc="自動判別", new_svc_name=""):
    """
    🌟 全ファイル収集スキャナー (マルチスレッド並列処理爆速化版)
    すべてのチャットおよびアセット（.py, .zip等）を漏れなく一斉並列スキャンしてAI種別を判定します。
    """
    if not os.path.exists(src_dir):
        return [], 0, []

    all_files = [f for f in os.listdir(src_dir) if not f.startswith(".") and not os.path.isdir(os.path.join(src_dir, f))]

    scanned_chats = []
    chat_file_names = set()

    # 🌟 マルチスレッド（ThreadPoolExecutor）による全ファイルの並列一斉スキャン！
    if all_files:
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_worker_read_and_parse, os.path.join(src_dir, fn), fn, parse_mode, declared_svc, new_svc_name)
                for fn in all_files
            ]
            for future in as_completed(futures):
                parsed_chat, _ = future.result()
                if parsed_chat:
                    scanned_chats.append(parsed_chat)
                    chat_file_names.add(parsed_chat["file_name"])

    local_media_files = [f for f in all_files if f not in chat_file_names]

    for chat in scanned_chats:
        chat["local_media_files"] = local_media_files

    return scanned_chats, len(all_files), local_media_files