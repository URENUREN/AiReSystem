# -*- coding: utf-8 -*-
# gemini_web.py - Gemini Web (日本語ファイル名・マイアクティビティ完全捕捉 ＆ マルチスレッド並列処理爆速フュージョン版)
import os
import json
import datetime
import re
import shutil
import html as html_module
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def parse_utc_to_jst(utc_str):
    if not utc_str: return ""
    try:
        clean_time = re.sub(r'\.\d+Z$', '', utc_str).replace('T', ' ').replace('Z', '')
        utc_dt = datetime.datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
        jst_dt = utc_dt + datetime.timedelta(hours=9)
        return jst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return utc_str


def parse_utc_datetime(utc_str):
    if not utc_str: return None
    try:
        clean_time = re.sub(r'\.\d+Z$', '', utc_str).replace('T', ' ').replace('Z', '')
        return datetime.datetime.strptime(clean_time, "%Y-%m-%d %H:%M:%S")
    except: return None


def sanitize_filename(filename):
    if not filename: return "Gemini_Chat"
    clean_name = re.sub(r'[\\/*?:"<>|]', "_", str(filename))
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    return clean_name[:60] if clean_name else "Gemini_Chat"


def html_to_markdown(html_str):
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


def extract_hash_id(filename):
    m = re.search(r'[\-_]([a-f0-9]{12,16})\b', filename, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def _worker_parse_html_cell(cell, local_media_files, hash_to_real_files):
    """🌟 マルチスレッド用 HTMLアクティビティセル解析ワーカー"""
    try:
        cell_str = str(cell)

        u_match = re.search(r'送信したメッセージ:\s*([\s\S]*?)(?:添付ファイル|\d{4}/\d{2}/\d{2}|$|<div)', cell_str)
        raw_prompt = html_to_markdown(u_match.group(1)) if u_match else ""
        clean_prompt = re.sub(r'\s+', '', raw_prompt).strip()

        t_match = re.search(r'(\d{4}/\d{2}/\d{2}\s+\d{1,2}:\d{2}:\d{2})', cell_str)
        time_str = t_match.group(1) if t_match else ""

        extracted_refs = set(re.findall(r'[\w\-\.\%\s\(\)\u3000-\u30ff\u4e00-\u9fff]+\.[a-zA-Z0-9]+', cell_str))
        
        resolved_files = set()
        for ref in extracted_refs:
            ref_clean = os.path.basename(ref.strip())
            ref_hash = extract_hash_id(ref_clean)

            if ref_clean in local_media_files:
                resolved_files.add(ref_clean)

            if ref_hash and ref_hash in hash_to_real_files:
                resolved_files.update(hash_to_real_files[ref_hash])

        for mf in local_media_files:
            if mf not in resolved_files and len(mf) > 10:
                mf_core = mf.split(".")[0]
                if mf_core in cell_str:
                    resolved_files.add(mf)

        if (clean_prompt or time_str) and resolved_files:
            return {
                "prompt_snippet": clean_prompt[:30],
                "time_str": time_str,
                "files": resolved_files
            }
    except: pass
    return None


def build_html_asset_map(html_path, local_media_files):
    """🌟 マルチスレッド並列処理対応 HTMLアセットマップ構築"""
    prompt_asset_map = []
    if not html_path or not os.path.exists(html_path):
        return prompt_asset_map

    hash_to_real_files = {}
    for rf in local_media_files:
        h_id = extract_hash_id(rf)
        if h_id:
            hash_to_real_files.setdefault(h_id, set()).add(rf)

    try:
        with open(html_path, "r", encoding="utf-8") as f: raw_html = f.read()

        if HAS_BS4:
            soup = BeautifulSoup(raw_html, "html.parser")
            outer_cells = soup.find_all("div", class_=lambda c: c and "outer-cell" in c)
        else:
            outer_cells = re.findall(r'<div class="outer-cell[\s\S]*?</div>\s*</div>\s*</div>', raw_html)

        if outer_cells:
            max_workers = min(32, (os.cpu_count() or 4) * 2)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_worker_parse_html_cell, cell, local_media_files, hash_to_real_files) for cell in outer_cells]
                for future in as_completed(futures):
                    res = future.result()
                    if res:
                        prompt_asset_map.append(res)

    except Exception as e:
        print("HTML asset map error:", e)

    return prompt_asset_map


def execute_gemini_splitter_fusion(json_path, html_path, output_dir, local_media_files=None):
    os.makedirs(output_dir, exist_ok=True)
    if local_media_files is None: local_media_files = []

    prompt_asset_map = build_html_asset_map(html_path, local_media_files)
    scanned_chats = []

    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f: data = json.load(f)

            raw_entries = []
            if isinstance(data, list): raw_entries = data
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list): raw_entries.extend(v)

            gemini_entries = [e for e in raw_entries if isinstance(e, dict) and ("gemini" in str(e.get("header", "")).lower() or "bard" in str(e.get("header", "")).lower() or "title" in e or "safeHtmlItem" in e)]

            sorted_entries = sorted(gemini_entries, key=lambda x: str(x.get("time", "")))
            threads = []
            current_thread = []
            last_dt = None

            for entry in sorted_entries:
                dt = parse_utc_datetime(entry.get("time", ""))
                if not current_thread:
                    current_thread.append(entry)
                elif dt and last_dt and (dt - last_dt).total_seconds() > 14400: # 4時間スレッド分割
                    threads.append(current_thread)
                    current_thread = [entry]
                else:
                    current_thread.append(entry)
                last_dt = dt
            if current_thread: threads.append(current_thread)

            for idx, thread in enumerate(threads):
                turns = []
                first_user_text = ""
                start_time_jst = parse_utc_to_jst(thread[0].get("time", ""))
                end_time_jst = parse_utc_to_jst(thread[-1].get("time", ""))

                for entry in thread:
                    time_raw = entry.get("time", "")
                    time_jst = parse_utc_to_jst(time_raw)

                    user_text = ""
                    title_val = entry.get("title", "")
                    if title_val:
                        user_text = re.sub(r'^(送信したメッセージ:\s*|「|」を検索)', '', str(title_val)).strip()

                    subtitles = entry.get("subtitles", [])
                    if not user_text and isinstance(subtitles, list):
                        for sub in subtitles:
                            if isinstance(sub, dict):
                                val = sub.get("value", "")
                                if val: user_text = str(val).strip(); break

                    if user_text and not first_user_text: first_user_text = user_text

                    model_text = ""
                    safe_html = entry.get("safeHtmlItem", [])
                    if isinstance(safe_html, list):
                        for item in safe_html:
                            if isinstance(item, dict):
                                html_code = item.get("html", "")
                                if html_code: model_text += html_to_markdown(html_code) + "\n\n"

                    matched_files_for_turn = set()
                    clean_user_snippet = re.sub(r'\s+', '', user_text)[:30]

                    for map_item in prompt_asset_map:
                        p_snip = map_item["prompt_snippet"]
                        t_str = map_item["time_str"]

                        if (clean_user_snippet and p_snip and (clean_user_snippet in p_snip or p_snip in clean_user_snippet)) or \
                           (t_str and time_jst and t_str[:13] in time_jst.replace("-", "/")):
                            matched_files_for_turn.update(map_item["files"])

                    media_tags = []
                    for m_fn in matched_files_for_turn:
                        ext = m_fn.split(".")[-1].lower() if "." in m_fn else ""
                        if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                            media_tags.append(f"\n![添付画像](./assets/{m_fn})\n")
                        elif ext in ["mp4", "webm"]:
                            media_tags.append(f'\n<video src="./assets/{m_fn}" controls width="420"></video>\n')
                        elif ext in ["wav", "mp3", "ogg"]:
                            media_tags.append(f'\n<audio src="./assets/{m_fn}" controls></audio>\n')
                        else:
                            media_tags.append(f'\n[📎 添付ファイル: {m_fn}](./assets/{m_fn})\n')

                    if media_tags: user_text += "\n" + "\n".join(media_tags)

                    contents_parts = []
                    if user_text: contents_parts.append({"role": "user", "parts": [{"text": user_text.strip()}]})
                    if model_text.strip(): contents_parts.append({"role": "model", "parts": [{"text": model_text.strip()}]})

                    if contents_parts:
                        turns.extend(contents_parts)

                if not turns: continue
                clean_title = sanitize_filename(first_user_text[:40] if first_user_text else f"Gemini_Chat_{idx+1}")

                split_json_path = os.path.join(output_dir, f"{clean_title}.json")
                out_struct = {
                    "title": clean_title,
                    "service": "Gemini",
                    "start_time": start_time_jst,
                    "end_time": end_time_jst,
                    "contents": turns
                }
                with open(split_json_path, "w", encoding="utf-8") as f_out:
                    json.dump(out_struct, f_out, ensure_ascii=False, indent=2)

                scanned_chats.append({
                    "file_name": f"{clean_title}.json",
                    "title": clean_title,
                    "service": "Gemini",
                    "model_id": "gemini-web-takeout",
                    "start_time": start_time_jst or "不明",
                    "end_time": end_time_jst or "不明",
                    "raw_json_data": out_struct,
                    "raw_text_data": json.dumps(out_struct, ensure_ascii=False),
                    "parsed_contents": turns,
                    "system_instruction": ""
                })

        except Exception as e:
            print("Fusion execution error:", e)

    return scanned_chats


def _worker_copy_asset(m_fn, src_m, dst_m):
    """🌟 マルチスレッド用 アセット並列コピーワーカー"""
    try:
        if src_m and os.path.exists(src_m) and not os.path.exists(dst_m):
            shutil.copy2(src_m, dst_m)
            return True
    except: pass
    return False


# ================= 🌟 メインスキャナー関数 (100%捕捉 ＆ マルチスレッド並列処理版) =================
def scan_gemini_web_directory(src_dir, parse_mode="すべての対応ファイル", declared_svc="自動判別", new_svc_name="", log_func=None):
    if not os.path.exists(src_dir):
        return [], 0, []

    all_files_map = {}
    for root_dir, _, files in os.walk(src_dir):
        for f in files:
            if not f.startswith(".") and not f.endswith(".py") and not f.endswith(".pyw"):
                all_files_map[f] = os.path.join(root_dir, f)

    json_file_path = None
    html_file_path = None

    # 🌟 1. マイアクティビティ (日本語/英語) ファイルの100%判定補着！
    for fn, fp in all_files_map.items():
        fn_lower = fn.lower()

        if fn_lower.endswith(".json"):
            if "activity" in fn_lower or "アクティビティ" in fn_lower or "myactivity" in fn_lower or "マイアクティビティ" in fn_lower:
                json_file_path = fp
            elif not json_file_path:
                try:
                    with open(fp, "r", encoding="utf-8") as check_f:
                        head_text = check_f.read(2000)
                        if "header" in head_text or "title" in head_text or "time" in head_text:
                            json_file_path = fp
                except: pass

        if fn_lower.endswith(".html") or fn_lower.endswith(".htm"):
            if "activity" in fn_lower or "アクティビティ" in fn_lower or "myactivity" in fn_lower or "マイアクティビティ" in fn_lower:
                html_file_path = fp
            elif not html_file_path:
                try:
                    with open(fp, "r", encoding="utf-8") as check_f:
                        head_text = check_f.read(2000)
                        if "outer-cell" in head_text or "送信したメッセージ" in head_text or "gemini" in head_text.lower():
                            html_file_path = fp
                except: pass

    # 一時作業フォルダー (__temp_gemini_split)
    temp_split_dir = os.path.join(src_dir, "__temp_gemini_split")
    if os.path.exists(temp_split_dir):
        try: shutil.rmtree(temp_split_dir)
        except: pass

    os.makedirs(temp_split_dir, exist_ok=True)

    local_media_files = [fn for fn in all_files_map.keys() if fn not in [os.path.basename(json_file_path or ""), os.path.basename(html_file_path or "")]]

    # 物理分割 ＆ フュージョン合体実行
    scanned_chats = execute_gemini_splitter_fusion(json_file_path, html_file_path, temp_split_dir, local_media_files)

    # 🌟 全アセットを一時分割フォルダへマルチスレッド一斉並列コピー！
    copy_tasks = []
    for m_fn in local_media_files:
        src_m = all_files_map.get(m_fn)
        dst_m = os.path.join(temp_split_dir, m_fn)
        if src_m and os.path.exists(src_m):
            copy_tasks.append((m_fn, src_m, dst_m))

    if copy_tasks:
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_worker_copy_asset, m_fn, src_m, dst_m) for m_fn, src_m, dst_m in copy_tasks]
            for _ in as_completed(futures): pass

    for chat in scanned_chats:
        chat["local_media_files"] = local_media_files

    return scanned_chats, len(all_files_map), local_media_files