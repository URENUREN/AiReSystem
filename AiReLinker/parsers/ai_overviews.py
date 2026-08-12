# -*- coding: utf-8 -*-
# ai_overviews.py - Google Search AI Overviews (旧SGE) 専用解析・HTML/JSON完全パース・全ファイルアセット収集プラグイン (完全復元＆マルチスレッド爆速化版)
import os
import json
import datetime
import re
import html as html_module
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


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
        return "AI_Overview_Chat"
    clean_name = re.sub(r'[\\/*?:"<>|]', "_", str(filename))
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    return clean_name[:60] if clean_name else "AI_Overview_Chat"


def html_to_markdown(html_str):
    """HTML装飾タグをMarkdownテキストへ自動変換"""
    if not html_str: return ""
    text = html_module.unescape(html_str)
    text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n**\1**\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", r"\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", r"\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", r"\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_ai_overviews_chat(file_path, file_name, raw_data, declared_svc="自動判別", new_svc_name=""):
    """
    単一のAI Overviews（Google検索AI / SGE）ログファイル (JSONまたはHTML) を高度パース
    """
    service_name = "AI Overviews" if declared_svc == "自動判別" else (new_svc_name if declared_svc == "新規追加..." else declared_svc)
    title = ""
    contents = []
    time_val = ""

    # 1. JSON構造体の高度解読
    try:
        data = json.loads(raw_data)
        if isinstance(data, dict):
            title = data.get("title", data.get("query", data.get("search_query", data.get("prompt", ""))))
            time_val = parse_utc_to_jst(data.get("time", data.get("createTime", data.get("timestamp", ""))))

            # 様々なネスト構造からの会話抽出
            if "contents" in data and isinstance(data["contents"], list):
                contents = data["contents"]
            elif "turns" in data and isinstance(data["turns"], list):
                contents = data["turns"]
            elif "generative_ai_response" in data:
                gen_resp = data["generative_ai_response"]
                q_text = title if title else "Google検索クエリ"
                ans_text = str(gen_resp)
                contents = [
                    {"role": "user", "parts": [{"text": q_text}]},
                    {"role": "model", "parts": [{"text": ans_text}]}
                ]
            elif "query" in data and "response" in data:
                contents = [
                    {"role": "user", "parts": [{"text": str(data["query"])}]},
                    {"role": "model", "parts": [{"text": str(data["response"])}]}
                ]
        elif isinstance(data, list):
            contents = data
    except:
        pass

    # 2. HTML形式 (Google Takeout 検索AIアクティビティ) のフォールバック解読
    if not contents and ("<html" in raw_data.lower() or "outer-cell" in raw_data or "ai overview" in raw_data.lower()):
        try:
            if HAS_BS4:
                soup = BeautifulSoup(raw_data, "html.parser")
                query_el = soup.find(class_=lambda c: c and "query" in c)
                title = query_el.get_text().strip() if query_el else ""
                
                body_text = html_to_markdown(raw_data)
                if body_text:
                    contents = [
                        {"role": "user", "parts": [{"text": title if title else "Google AI概要検索"}]},
                        {"role": "model", "parts": [{"text": body_text}]}
                    ]
            else:
                m_q = re.search(r'検索クエリ:\s*(.*?)(?:<|$)', raw_data)
                if m_q: title = m_q.group(1).strip()
                body_text = html_to_markdown(raw_data)
                if body_text:
                    contents = [
                        {"role": "user", "parts": [{"text": title if title else "Google AI概要検索"}]},
                        {"role": "model", "parts": [{"text": body_text}]}
                    ]
        except: pass

    if not contents:
        return None

    if not title:
        title = os.path.splitext(file_name)[0]

    if not time_val:
        try:
            mtime = os.path.getmtime(file_path)
            time_val = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_val = "不明"

    return {
        "file_name": file_name,
        "title": sanitize_filename(title),
        "service": service_name,
        "model_id": "google-search-ai-overviews",
        "start_time": time_val,
        "end_time": time_val,
        "raw_json_data": raw_data if isinstance(raw_data, dict) else {},
        "raw_text_data": raw_data,
        "parsed_contents": contents,
        "system_instruction": ""
    }


def _worker_parse_ai_overview_file(file_path, file_name, parse_mode, declared_svc, new_svc_name):
    """🌟 マルチスレッド用 1ファイルパースワーカー"""
    if parse_mode == "JSONファイルのみ (.json)" and not file_name.endswith(".json"):
        return None
    elif parse_mode == "Markdownファイルのみ (.md)" and not file_name.endswith(".md"):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = f.read()
        parsed = parse_ai_overviews_chat(file_path, file_name, raw_data, declared_svc, new_svc_name)
        if parsed:
            return parsed
    except: pass
    return None


def scan_ai_overviews_directory(src_dir, parse_mode="すべての対応ファイル", declared_svc="自動判別", new_svc_name="", log_func=None):
    """
    🌟 AI Overviews全ファイル収集スキャナー (完全復元 ＆ マルチスレッド並列処理爆速化版)
    """
    if not os.path.exists(src_dir):
        return [], 0, []

    all_files = [f for f in os.listdir(src_dir) if not f.startswith(".") and not os.path.isdir(os.path.join(src_dir, f))]

    scanned_chats = []
    chat_file_names = set()

    # 🌟 マルチスレッド（ThreadPoolExecutor）で全一斉並列スキャン
    if all_files:
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_worker_parse_ai_overview_file, os.path.join(src_dir, fn), fn, parse_mode, declared_svc, new_svc_name)
                for fn in all_files
            ]
            for future in as_completed(futures):
                parsed = future.result()
                if parsed:
                    scanned_chats.append(parsed)
                    chat_file_names.add(parsed["file_name"])

    local_media_files = [f for f in all_files if f not in chat_file_names]

    for chat in scanned_chats:
        chat["local_media_files"] = local_media_files

    return scanned_chats, len(all_files), local_media_files