# -*- coding: utf-8 -*-
# AiReImporterLogic.py - スキャン・インポート調停・アセット最適化実行ロジック (マルチスレッド並列解析爆速化版)
import os
import json
import datetime
import shutil
import threading
import urllib.parse
import re
import hashlib
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import messagebox, filedialog

from parsers.google_ai_studio import (
    scan_google_ai_studio_directory,
    sanitize_filename,
    normalize_text
)

# 🌟 Gemini Web 用スキャナーの動的安全インポート
try:
    from parsers.gemini_web import scan_gemini_web_directory
    HAS_GEMINI_WEB_PARSER = True
except ImportError:
    HAS_GEMINI_WEB_PARSER = False

# AI Overviews 用スキャナーの動的安全インポート
try:
    from parsers.ai_overviews import scan_ai_overviews_directory
    HAS_AI_OVERVIEWS_PARSER = True
except ImportError:
    HAS_AI_OVERVIEWS_PARSER = False

from AiReImporterAssets import (
    compact_and_reindex_master_assets,
    process_inline_and_local_assets,
    salvage_unlinked_assets,
    count_inline_data
)

def update_monolith_record(thread_id, service_name, true_start, true_end):
    """project_monolith.json に実際の会話時間を記録"""
    monolith_path = "./project_monolith.json"
    records = []
    if os.path.exists(monolith_path):
        try:
            with open(monolith_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except: pass

    found = False
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for rec in records:
        if rec.get("thread_id") == thread_id:
            rec["true_start_time"] = true_start
            rec["true_end_time"] = true_end
            if "history" not in rec: rec["history"] = []
            rec["history"].append({
                "save_index": len(rec["history"]) + 1,
                "saved_at": now_str,
                "current_end_time": true_end,
                "start_theme": "一括インポート基準マスター",
                "end_theme": "一括インポート基準マスター",
                "milestone": "調停インポーターからマージ"
            })
            found = True
            break

    if not found:
        records.append({
            "thread_id": thread_id,
            "theme_folder": service_name,
            "true_start_time": true_start,
            "true_end_time": true_end,
            "url": "https://manual-import-log/",
            "history": [{
                "save_index": 1,
                "saved_at": now_str,
                "current_end_time": true_end,
                "start_theme": "一括インポート新規マージ",
                "end_theme": "一括インポート新規マージ",
                "milestone": "新規インポート"
            }]
        })

    try:
        with open(monolith_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except: pass

def run_scan_process(ui):
    """インポート元フォルダの非同期超高速スキャン (動的パーサー切替 ＆ 代表フォールバック対応)"""
    src = ui.src_dir_var.get().strip()
    if not src or not os.path.exists(src):
        messagebox.showwarning("警告", "有効なフォルダを参照してください。")
        return

    ui.is_analyzed = False
    ui.btn_scan.config(state="disabled")
    ui.tree.delete(*ui.tree.get_children())
    ui.scanned_chats_data.clear()
    ui.log("🔍 インポート元の超高速事前スキャンを開始します...")

    svc_selected = ui.service_var.get().strip()
    parse_mode = ui.parse_mode_var.get()
    new_svc = ui.new_svc_entry.get().strip()

    def scan_thread():
        try:
            all_files = [f for f in os.listdir(src) if not f.startswith(".") and not os.path.isdir(os.path.join(src, f))]
        except Exception as e:
            ui.log(f"❌ フォルダ読み込みエラー: {e}")
            ui.after(0, lambda: ui.btn_scan.config(state="normal"))
            return

        ui.after(0, lambda: ui.progress_bar.config(value=0, maximum=len(all_files)))

        chats = []
        total_files = len(all_files)
        local_media_files = []

        # 🌟 1. ユーザー選択に応じたスキャナー動的切り替えロジック！
        if "gemini" in svc_selected.lower() and HAS_GEMINI_WEB_PARSER:
            ui.log("📡 Gemini専用解析パーサー (gemini_web.py) を実行中...")
            chats, total_files, local_media_files = scan_gemini_web_directory(src, parse_mode, svc_selected, new_svc)
        elif ("overview" in svc_selected.lower() or "検索" in svc_selected.lower()) and HAS_AI_OVERVIEWS_PARSER:
            ui.log("📡 AI Overviews専用解析パーサー (ai_overviews.py) を実行中...")
            chats, total_files, local_media_files = scan_ai_overviews_directory(src, parse_mode, svc_selected, new_svc)
        else:
            # 他サービス（ChatGPT / Claude / NotebookLM 等）または自動判別の場合
            ui.log(f"📡 AIサービス解析パーサー ({svc_selected}) を実行中...")
            chats, total_files, local_media_files = scan_google_ai_studio_directory(src, parse_mode, svc_selected, new_svc)

            # 🌟 2. 自動判別モードで0件の場合、各種パーサーの可能性を考慮してセカンドトライ！
            if not chats and HAS_AI_OVERVIEWS_PARSER:
                ui.log("🔄 セカンドトライ: AI Overviewsデータ構造の自動検証を実行中...")
                g_chats, g_total, g_media = scan_ai_overviews_directory(src, parse_mode, svc_selected, new_svc)
                if g_chats:
                    chats, total_files, local_media_files = g_chats, g_total, g_media
            
            if not chats and (svc_selected in ["自動判別", "Gemini"]) and HAS_GEMINI_WEB_PARSER:
                ui.log("🔄 セカンドトライ: Gemini Takeoutデータ構造の自動検証を実行中...")
                g_chats, g_total, g_media = scan_gemini_web_directory(src, parse_mode, svc_selected, new_svc)
                if g_chats:
                    chats, total_files, local_media_files = g_chats, g_total, g_media

        for idx, item in enumerate(chats):
            percentage = int((idx + 1) / len(chats) * 100) if chats else 100
            bar_len = 10
            filled_len = int(bar_len * (idx + 1) // len(chats)) if chats else 10
            bar_str = "█" * filled_len + "░" * (bar_len - filled_len)

            ui.after(0, lambda v=idx+1: ui.progress_bar.config(value=v))
            ui.log(f"🔄 スキャン中: {idx+1}/{len(chats)} 件 ({percentage}%) [{bar_str}] - 『{item['title'][:25]}...』")

        ui.scanned_chats_data = chats

        ui.after(0, lambda: ui.update_dashboard_counts(total_files, len(chats), 0, len(local_media_files), 0, 0))

        def gui_update():
            for idx, item in enumerate(ui.scanned_chats_data):
                ui.tree.insert("", "end", iid=str(idx), values=("☑", "⌛ スキャン済", item["title"], item["service"], item["end_time"], " - ", " - ", " - "))
            ui.btn_scan.config(state="normal")
            ui.btn_run_import.config(state="normal")
            ui.btn_import_other.config(state="normal")
            ui.btn_deep_analyze.config(state="normal")
            ui.log(f"🎉 スキャン完了: AI会話ログ 【{len(chats)} 件】 / 全アセット 【{len(local_media_files)} 件】 を検出しました。（『アセット詳細解析』を実行してください）")

        ui.after(0, gui_update)

    threading.Thread(target=scan_thread, daemon=True).start()

def _worker_deep_analyze_chat(item, local_media_files, duplicate_files_set):
    """🌟 マルチスレッド用 1チャットのアセット詳細解析ワーカー"""
    title = item.get("title", "無題")
    data = item.get("raw_json_data", {})

    struct_asset_count = count_inline_data(data)

    decoded_raw_data = ""
    try: decoded_raw_data = json.dumps(data, ensure_ascii=False)
    except: decoded_raw_data = item.get("raw_text_data", "")

    raw_txt = item.get("raw_text_data", "")

    matched_assets = []
    for m_file in local_media_files:
        clean_m_file = re.sub(r'\(\d+\)\.', '.', m_file)
        clean_m_file_encoded = urllib.parse.quote(clean_m_file)
        clean_m_file_safe = clean_m_file.replace(" ", "%20")
        m_file_encoded = urllib.parse.quote(m_file)
        m_file_safe = m_file.replace(" ", "%20")

        if (m_file in raw_txt) or (m_file in decoded_raw_data) or (m_file_encoded in raw_txt) or (m_file_safe in raw_txt) or \
           (clean_m_file in raw_txt) or (clean_m_file in decoded_raw_data) or (clean_m_file_encoded in raw_txt) or (clean_m_file_safe in raw_txt):
            matched_assets.append(m_file)

    asset_refs = set(re.findall(r'(?:!\[.*?\]\(\.\/assets\/|src=["\']\.\/assets\/|assets\/)([\w\-\.\%\s\(\)]+\.[a-zA-Z0-9]+)', raw_txt, re.IGNORECASE))

    chat_missing_files = []
    missing_links = []
    for ref_fn in asset_refs:
        decoded_ref = urllib.parse.unquote(ref_fn)
        if decoded_ref not in local_media_files and ref_fn not in local_media_files:
            chat_missing_files.append(decoded_ref)
            missing_links.append({"file": decoded_ref, "chat": title})

    chat_dup_count = sum(1 for m in matched_assets if m in duplicate_files_set)
    total_asset_count = max(struct_asset_count, len(matched_assets))

    item["matched_assets"] = matched_assets
    item["asset_count"] = total_asset_count
    item["dup_count"] = chat_dup_count
    item["missing_count"] = len(chat_missing_files)

    return {
        "item": item,
        "title": title,
        "matched_assets": matched_assets,
        "total_asset_count": total_asset_count,
        "chat_dup_count": chat_dup_count,
        "chat_missing_files": chat_missing_files,
        "missing_links": missing_links
    }

def run_deep_analysis_process(ui):
    """アセット詳細解析スレッド (マルチスレッド並列スキャン爆速化版)"""
    src = ui.src_dir_var.get().strip()
    if not src or not os.path.exists(src): return

    selected_indices = []
    for item_id in ui.tree.get_children():
        vals = ui.tree.item(item_id, "values")
        if vals[0] == "☑":
            selected_indices.append((int(item_id), item_id))

    if not selected_indices:
        messagebox.showwarning("警告", "アセット解析を行うチャットにチェックを入れてください。")
        return

    ui.btn_deep_analyze.config(state="disabled")
    ui.btn_run_import.config(state="disabled")
    ui.log("🧬 [アセット詳細解析] を開始します... (マルチスレッド並列処理化)")

    def deep_scan_thread():
        chats_files = set(c.get("file_name", "") for c in ui.scanned_chats_data)
        all_files = [f for f in os.listdir(src) if not f.startswith(".") and not os.path.isdir(os.path.join(src, f))]
        local_media_files = [f for f in all_files if f not in chats_files]

        # 重複ハッシュ判定
        hashes = {}
        duplicate_files_set = set()
        for mf in local_media_files:
            p = os.path.join(src, mf)
            try:
                with open(p, "rb") as fh:
                    f_hash = hashlib.md5(fh.read()).hexdigest()
                hashes.setdefault(f_hash, []).append(mf)
            except: pass

        duplicate_count = 0
        for f_hash, files in hashes.items():
            if len(files) > 1:
                duplicate_count += (len(files) - 1)
                for dup_f in files[1:]:
                    duplicate_files_set.add(dup_f)

        ui.last_duplicate_map = hashes
        total_linked_assets = set()
        missing_links_map = set()
        missing_links_list = []

        ui.is_analyzed = True
        ui.after(0, lambda: ui.progress_bar.config(value=0, maximum=len(selected_indices)))

        # 🌟 マルチスレッド並列一斉解析のタスク生成
        tasks = []
        for s_idx, item_id in selected_indices:
            item = ui.scanned_chats_data[s_idx]
            tasks.append((item_id, item))

            current_tree_vals = ui.tree.item(item_id, "values")
            ui.after(0, lambda i_id=item_id, cv=current_tree_vals: ui.tree.item(i_id, values=(cv[0], "🔄 解析中", cv[2], cv[3], cv[4], cv[5], cv[6], cv[7])))

        max_workers = min(32, (os.cpu_count() or 4) * 2)
        completed_cnt = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(_worker_deep_analyze_chat, item, local_media_files, duplicate_files_set): item_id
                for item_id, item in tasks
            }

            for future in as_completed(future_to_item):
                item_id = future_to_item[future]
                completed_cnt += 1
                ui.after(0, lambda v=completed_cnt: ui.progress_bar.config(value=v))

                res = future.result()
                if res:
                    title = res["title"]
                    matched_assets = res["matched_assets"]
                    total_asset_count = res["total_asset_count"]
                    chat_dup_count = res["chat_dup_count"]
                    chat_missing_files = res["chat_missing_files"]

                    for m in matched_assets:
                        total_linked_assets.add(m)

                    for m_link in res["missing_links"]:
                        key = (m_link["file"], m_link["chat"])
                        if key not in missing_links_map:
                            missing_links_map.add(key)
                            missing_links_list.append(m_link)

                    current_tree_vals = ui.tree.item(item_id, "values")
                    ui.after(0, lambda i_id=item_id, cv=current_tree_vals, lc=total_asset_count, dc=chat_dup_count, mc=len(chat_missing_files):
                        ui.tree.item(i_id, values=(cv[0], "✅ 解析済", cv[2], cv[3], cv[4], f"{lc} 件", f"{dc} 件", f"{mc} 件")))

                    cur_stray = len(local_media_files) - len(total_linked_assets)
                    cur_missing = len(missing_links_list)
                    ui.after(0, lambda l=len(total_linked_assets), s=cur_stray, d=duplicate_count, m=cur_missing:
                        ui.update_dashboard_counts(len(all_files), len(ui.scanned_chats_data), l, s, d, m))

                    ui.log(f"🧬 [アセット解析] {completed_cnt}/{len(selected_indices)} 件: 『{title[:20]}...』 (成功: {total_asset_count} / 重複: {chat_dup_count} / Missing: {len(chat_missing_files)})")

        ui.last_linked_assets = total_linked_assets
        ui.last_missing_assets = [f for f in local_media_files if f not in total_linked_assets]
        ui.last_missing_links = missing_links_list

        stray_files_count = len(local_media_files) - len(total_linked_assets)

        ui.after(0, lambda: ui.update_dashboard_counts(len(all_files), len(ui.scanned_chats_data), len(total_linked_assets), stray_files_count, duplicate_count, len(missing_links_list)))

        def complete_gui():
            ui.btn_deep_analyze.config(state="normal")
            ui.btn_run_import.config(state="normal")
            ui.btn_import_other.config(state="normal")
            ui.log(f"🎉 [解析完了] アセット詳細解析が完了しました。（成功: {len(total_linked_assets)} / 迷子: {stray_files_count} / 重複: {duplicate_count} / Missing: {len(missing_links_list)}）")

        ui.after(0, complete_gui)

    threading.Thread(target=deep_scan_thread, daemon=True).start()

def run_import_process(ui, override_save_dir=None):
    """基準マスターログ調停インポート実行スレッド (真の会話日時書き込み対応)"""
    try:
        src_raw = ui.src_dir_var.get().strip().strip('"').strip("'")
        src = os.path.normpath(src_raw) if src_raw else ""

        if not src or not os.path.exists(src):
            messagebox.showwarning("警告", "有効なインポート元フォルダを指定してください。")
            return

        selected_indices = []
        for item_id in ui.tree.get_children():
            vals = ui.tree.item(item_id, "values")
            if vals[0] == "☑":
                selected_indices.append((int(item_id), item_id))

        if not selected_indices:
            messagebox.showwarning("警告", "インポートするチャットにチェックを入れてください。")
            return

        import_body = ui.var_import_body.get()
        import_media = ui.var_import_media.get()
        policy = ui.policy_var.get()

        raw_dest = override_save_dir if override_save_dir else ui.dest_dir_var.get().strip()
        target_save_dir = os.path.normpath(raw_dest.strip().strip('"').strip("'")) if raw_dest else os.path.normpath(getattr(ui, 'save_dir', './logs'))

        source_op = ui.policy_src_op.get()
        stray_op = ui.policy_stray_op.get()

        run_mode_var = getattr(ui, 'run_mode_var', None)
        run_mode = run_mode_var.get() if run_mode_var else "auto"

        if not import_body and not import_media:
            messagebox.showwarning("警告", "本文、アセットのいずれかは必ずチェックを入れてください。")
            return

        ui.btn_run_import.config(state="disabled")
        ui.btn_import_other.config(state="disabled")
        ui.log(f"🔨 調停インポートプロセスを始動しました。（選択チャット数: {len(selected_indices)} 件 / モード: {run_mode}）")

    except Exception as e_init:
        err_msg = traceback.format_exc()
        messagebox.showerror("インポート起動エラー", f"インポート処理の初期化中にエラーが発生しました:\n{e_init}\n\n詳細:\n{err_msg[:300]}")
        ui.btn_run_import.config(state="normal")
        return

    def import_run_thread():
        try:
            imported_count = 0
            merged_count = 0
            imported_chat_folders = []
            ui.manual_compact_targets.clear()

            chats_files = set(c.get("file_name", "") for c in ui.scanned_chats_data)
            all_files = [f for f in os.listdir(src) if not f.startswith(".") and not os.path.isdir(os.path.join(src, f))]
            local_media_files = [f for f in all_files if f not in chats_files]

            total_linked_assets = set()
            processed_source_files = set()

            ui.after(0, lambda: ui.progress_bar.config(value=0, maximum=len(selected_indices)))

            for idx, (s_idx, item_id) in enumerate(selected_indices):
                ui.after(0, lambda v=idx+1: ui.progress_bar.config(value=v))

                item = ui.scanned_chats_data[s_idx]
                chat_title_sanitized = sanitize_filename(item.get("title", "無題"))
                service_name = item.get("service", "Google AI Studio")

                chat_folder_path = os.path.join(target_save_dir, service_name, chat_title_sanitized, "importer")
                assets_folder_path = os.path.join(chat_folder_path, "assets")

                raw_filepath = os.path.join(chat_folder_path, f"raw_{chat_title_sanitized}.md")

                current_tree_vals = ui.tree.item(item_id, "values")

                if os.path.exists(raw_filepath) and policy == "skip":
                    ui.log(f"🧬 [上書きスキップ] 既存ログを神聖保護し、『{chat_title_sanitized}』をスキップしました。")
                    ui.after(0, lambda i_id=item_id, cv=current_tree_vals: ui.tree.item(i_id, values=(cv[0], "✅ スキップ", cv[2], cv[3], cv[4], cv[5], cv[6], cv[7]), tags=("success",)))
                    continue

                os.makedirs(chat_folder_path, exist_ok=True)
                os.makedirs(assets_folder_path, exist_ok=True)

                ui.after(0, lambda i_id=item_id, cv=current_tree_vals: ui.tree.item(i_id, values=(cv[0], "🔄 処理中", cv[2], cv[3], cv[4], cv[5], cv[6], cv[7])))
                ui.log(f"🔨 調停処理中 ({idx+1}/{len(selected_indices)}): 『{chat_title_sanitized}』...")

                matched_assets = item.get("matched_assets")
                if matched_assets is None:
                    matched_assets = []
                    decoded_raw_data = ""
                    try: decoded_raw_data = json.dumps(item.get("raw_json_data", {}), ensure_ascii=False)
                    except: decoded_raw_data = item.get("raw_text_data", "")

                    for m_file in local_media_files:
                        clean_m_file = re.sub(r'\(\d+\)\.', '.', m_file)
                        clean_m_file_encoded = urllib.parse.quote(clean_m_file)
                        clean_m_file_safe = clean_m_file.replace(" ", "%20")
                        m_file_encoded = urllib.parse.quote(m_file)
                        m_file_safe = m_file.replace(" ", "%20")

                        raw_txt = item.get("raw_text_data", "")
                        if (m_file in raw_txt) or (m_file in decoded_raw_data) or (m_file_encoded in raw_txt) or (m_file_safe in raw_txt) or \
                           (clean_m_file in raw_txt) or (clean_m_file in decoded_raw_data) or (clean_m_file_encoded in raw_txt) or (clean_m_file_safe in raw_txt):
                            matched_assets.append(m_file)
                            total_linked_assets.add(m_file)

                # アセットのコピー・移動
                if import_media and matched_assets:
                    for m_file in matched_assets:
                        src_media_path = os.path.join(src, m_file)
                        dst_media_path = os.path.join(assets_folder_path, m_file)
                        try:
                            shutil.copy2(src_media_path, dst_media_path)
                            if source_op == "cut":
                                processed_source_files.add(src_media_path)
                        except: pass

                # 本文Markdownの構築
                if import_body:
                    contents = item.get("parsed_contents", [])
                    system_instruction = item.get("system_instruction", "")

                    # 🌟 実際の会話時間をフロントマターに正確に継承！
                    start_t = item.get("start_time", item.get("end_time", "不明"))
                    end_t = item.get("end_time", "不明")

                    md_lines = [
                        "---",
                        f'ai_service: "{service_name}"',
                        f'model: "{item.get("model_id", "gemini-1.5-flash")}"',
                        'mark: "☆ 無し"',
                        'tags: ["インポート"]',
                        f'true_start_time: "{start_t}"',
                        f'true_end_time: "{end_t}"',
                        "---",
                        f"\n### [USER] インポート基準マスターログ: {chat_title_sanitized}\n"
                    ]

                    if system_instruction:
                        md_lines.append(f"> ⚙️ **System Instruction:**\n> {system_instruction}\n")

                    asset_counter = 1
                    for turn in contents:
                        role = turn.get("role", "unknown")
                        disp_role = "👤 USER" if role == "user" else "🤖 MODEL"
                        parts = turn.get("parts", [])

                        part_text, asset_counter = process_inline_and_local_assets(parts, assets_folder_path, asset_counter)

                        if import_media and matched_assets:
                            for m_file in matched_assets:
                                m_file_encoded = urllib.parse.quote(m_file)
                                m_file_safe = m_file.replace(" ", "%20")
                                if m_file in part_text or m_file_encoded in part_text or m_file_safe in part_text:
                                    ext = m_file.split(".")[-1].lower()
                                    target_replace = m_file if m_file in part_text else (m_file_encoded if m_file_encoded in part_text else m_file_safe)
                                    if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                                        part_text = part_text.replace(target_replace, f"\n![添付メディア](./assets/{m_file})\n")
                                    elif ext in ["mp3", "wav", "ogg"]:
                                        part_text = part_text.replace(target_replace, f"\n<audio src=\"./assets/{m_file}\" controls></audio>\n")
                                    elif ext in ["mp4"]:
                                        part_text = part_text.replace(target_replace, f"\n<video src=\"./assets/{m_file}\" controls width=\"420\"></video>\n")

                        if part_text.strip():
                            md_lines.append(f"### {disp_role}\n{part_text.strip()}\n")

                    new_raw_markdown = "\n".join(md_lines)

                    # 重ね合わせマージポリシー
                    if os.path.exists(raw_filepath) and policy == "merge":
                        ui.log("🧬 [重ね合わせマージ] 既存マスターログとの重複・欠損箇所を調停接続中...")
                        try:
                            with open(raw_filepath, "r", encoding="utf-8") as f: old_raw_markdown = f.read()
                            old_turns = old_raw_markdown.split("### ")
                            new_turns = new_raw_markdown.split("### ")
                            clean_turns = [old_turns[0]]
                            for ot in old_turns[1:]: clean_turns.append("### " + ot)
                            for nt in new_turns[1:]:
                                nt_text_only = "\n".join(nt.split("\n")[1:])
                                if normalize_text(nt_text_only) not in normalize_text(old_raw_markdown):
                                    clean_turns.append("### " + nt)
                                    merged_count += 1
                            new_raw_markdown = "".join(clean_turns)
                            ui.log("✅ [マージ成功] 新旧ログの不足箇所を相互補完して完全データに復元しました。")
                        except Exception as e:
                            ui.log(f"❌ マージエラー: {e}")

                    with open(raw_filepath, "w", encoding="utf-8") as out_f:
                        out_f.write(new_raw_markdown)

                final_assets_num = 0
                if run_mode == "auto":
                    if import_media:
                        _, final_assets_num, _ = compact_and_reindex_master_assets(chat_folder_path, raw_filepath)
                else:
                    ui.manual_compact_targets.append((chat_folder_path, raw_filepath, item_id, current_tree_vals))
                    final_assets_num = len(matched_assets)

                if source_op == "cut":
                    processed_source_files.add(os.path.join(src, item.get("file_name", "")))

                # 🌟 真の開始・終了日時を記録
                update_monolith_record(chat_title_sanitized, service_name, start_t, end_t)

                state_label = "✅ 完了" if run_mode == "auto" else "✅ 変換済"
                ui.after(0, lambda i_id=item_id, text=chat_title_sanitized, svc=service_name, t_end=end_t, a_cnt=final_assets_num, dc=item.get("dup_count", "-"), mc=item.get("missing_count", "-"), sl=state_label:
                    ui.tree.item(i_id, values=("☑", sl, text, svc, t_end, f"{a_cnt} 件", f"{dc} 件" if dc != "-" else "-", f"{mc} 件" if mc != "-" else "-"), tags=("success",)))

                imported_count += 1
                imported_chat_folders.append(chat_folder_path)

            total_stray_assets = [f for f in local_media_files if f not in total_linked_assets]
            if stray_op == "salvage" and total_stray_assets:
                salvaged_cnt, p_files = salvage_unlinked_assets(src, target_save_dir, total_stray_assets, source_op, service_name)
                processed_source_files.update(p_files)
                ui.log(f"✅ [救出完了] {salvaged_cnt} 件の迷子データを「__unlinked_salvage/」に安全に救出し終えました。")

            if source_op == "cut" and processed_source_files:
                deleted_err = 0
                for d_file in processed_source_files:
                    if os.path.exists(d_file):
                        try: os.remove(d_file)
                        except: deleted_err += 1
                ui.log(f"✅ [整理完了] 切り取り完了。処理の終わったデータは綺麗に消え去りました。")

            ui.log(f"🎉 インポート調停プロセス完了: {imported_count} 件成功、マージ補完 {merged_count} 件。")

            if ui.main_app:
                if hasattr(ui.main_app, 'portal_app'): ui.main_app.portal_app.refresh_portal_data()
                if hasattr(ui.main_app, 'timeline_app'): ui.main_app.timeline_app.refresh_timeline_data()

            ui.after(0, lambda: ui.btn_compact_assets.config(state="normal"))
            ui.after(0, lambda: ui.btn_run_import.config(state="normal"))
            ui.after(0, lambda: ui.btn_import_other.config(state="normal"))

            if run_mode == "step" and ui.manual_compact_targets:
                ui.log("✅ [ステップ判定] 本文のMarkdown変換が完了しました。[🔨 アセット最適化を実行] ボタンを押して最適化を実行してください。")
                return

            def show_imported_notice():
                messagebox.showinfo("インポート完了", f"一括インポート調停が正常に完了しました！（成功: {imported_count} 件）")

            ui.after(0, show_imported_notice)

        except Exception as e:
            err_detail = traceback.format_exc()
            ui.log(f"❌ インポート実行エラー: {e}")
            ui.after(0, lambda: messagebox.showerror("インポート実行エラー", f"インポート処理中に以下のエラーが発生しました:\n{e}\n\n詳細:\n{err_detail[:300]}"))
            ui.after(0, lambda: ui.btn_run_import.config(state="normal"))
            ui.after(0, lambda: ui.btn_import_other.config(state="normal"))

    threading.Thread(target=import_run_thread, daemon=True).start()

def run_compact_other_dir_process(ui):
    """別フォルダのアセット最適化スレッド"""
    target_dir = filedialog.askdirectory(title="アセット最適化を行うフォルダの選択")
    if not target_dir: return
    target_dir = os.path.abspath(target_dir)
    ui.log(f"🔨 [別フォルダ最適化] スキャン開始: {target_dir}")

    def other_compact_thread():
        count = 0
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                if f.startswith("raw_") and f.endswith(".md"):
                    raw_path = os.path.join(root, f)
                    assets_dir = os.path.join(root, "assets")
                    if os.path.exists(assets_dir):
                        compact_and_reindex_master_assets(root, raw_path)
                        count += 1
        ui.after(0, lambda: messagebox.showinfo("完了", f"指定されたフォルダ内の【{count} 件】のアセットを最適化しました！"))

    threading.Thread(target=other_compact_thread, daemon=True).start()

def run_manual_assets_compact_process(ui):
    """手動ステップ実行によるアセット最適化スレッド"""
    target_dir = ui.dest_dir_var.get().strip()
    if not target_dir or not os.path.exists(target_dir):
        messagebox.showwarning("警告", "有効なインポート保存先フォルダが指定されていません。")
        return

    ui.btn_compact_assets.config(state="disabled")
    ui.log(f"🔨 [アセット一括最適化] スキャン開始: {target_dir}")

    def compact_thread():
        cleaned_count = 0
        
        if ui.manual_compact_targets:
            for chat_folder_path, raw_filepath, item_id, current_tree_vals in ui.manual_compact_targets:
                chat_name = os.path.basename(os.path.dirname(chat_folder_path))
                ui.log(f"🔨 最適化中: 『{chat_name}』")
                _, final_assets_num, _ = compact_and_reindex_master_assets(chat_folder_path, raw_filepath)
                ui.after(0, lambda i_id=item_id, text=chat_name, svc=current_tree_vals[3], t_end=current_tree_vals[4], a_cnt=final_assets_num:
                    ui.tree.item(i_id, values=("☑", "✅ 完了", text, svc, t_end, f"{a_cnt} 件", current_tree_vals[6], current_tree_vals[7]), tags=("success",)))
                cleaned_count += 1
            ui.manual_compact_targets.clear()

        else:
            for root, dirs, files in os.walk(target_dir):
                for f in files:
                    if f.startswith("raw_") and f.endswith(".md"):
                        raw_path = os.path.join(root, f)
                        assets_dir = os.path.join(root, "assets")
                        if os.path.exists(assets_dir):
                            chat_name = os.path.basename(root)
                            ui.log(f"🔨 最適化中: 『{chat_name}』")
                            compact_and_reindex_master_assets(root, raw_path)
                            cleaned_count += 1

        ui.log(f"🎉 最適化完了: {cleaned_count} 件のチャットアセットの重複排除および連番リインデックスを適用しました！")
        ui.after(0, lambda: ui.btn_compact_assets.config(state="normal"))
        ui.after(0, lambda: messagebox.showinfo("完了", f"保存先フォルダ内の【{cleaned_count} 件】のチャットアセットを重複排除＆連番最適化しました！"))

    threading.Thread(target=compact_thread, daemon=True).start()

def run_batch_summary_kick(ui, chat_folders):
    """一括要約のキックスレッド"""
    pass