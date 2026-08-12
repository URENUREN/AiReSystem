# -*- coding: utf-8 -*-
# AiReImporterAssets.py - アセット抽出・重複排除・隙間ゼロ連番最適化・サルベージエンジン (マルチスレッド並列処理爆速化版)
import os
import re
import hashlib
import shutil
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed

def detect_file_type(data):
    """バイナリヘッダー（マジックナンバー）から拡張子とMIMEタイプを正確に判定"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    elif data.startswith(b"\xff\xd8"): 
        return "jpg", "image/jpeg"
    elif data.startswith(b"GIF8"):
        return "gif", "image/gif"
    elif data.startswith(b"RIFF") and b"WEBP" in data[8:12]:
        return "webp", "image/webp"
    elif data.startswith(b"BM"):
        return "bmp", "image/bmp"
    elif data.startswith(b"ID3") or data.startswith(b"\xff\xfb") or data.startswith(b"\xff\xf3") or data.startswith(b"\xff\xf2"):
        return "mp3", "audio/mp3"
    elif data.startswith(b"RIFF") and b"WAVE" in data[8:12]:
        return "wav", "audio/wav"
    elif b"ftyp" in data[4:16]:
        return "mp4", "video/mp4"
    elif data.startswith(b"OggS"):
        return "ogg", "audio/ogg"
    elif data.startswith(b"PK\x03\x04"):
        return "zip", "application/zip"
    elif data.startswith(b"%PDF"):
        return "pdf", "application/pdf"
    
    if data.startswith(b"<!DOCTYPE") or data.startswith(b"<html") or data.startswith(b'{"error"') or data.startswith(b"Unauthorized"):
        return None, None
        
    return "bin", "application/octet-stream"

def count_inline_data(data):
    """JSON構造体の中にある Base64 インラインデータの個数を再帰カウント"""
    count = 0
    if isinstance(data, dict):
        if "mimeType" in data and "data" in data:
            return 1
        for k, v in data.items():
            count += count_inline_data(v)
    elif isinstance(data, list):
        for item in data:
            count += count_inline_data(item)
    return count

def select_best_survivor(files):
    """
    🌟 【カッコなしシンプル名最優先の代表選出エンジン】
    重複ファイル群から生き残りを選ぶ優先順位：
    1. '(1)' や '(2)' などのカッコ付きコピー番号が付いていないこと（最優先！）
    2. ファイル名（文字数）が短くシンプルであること
    3. アルファベット順
    """
    def rank_key(fn):
        has_paren = 1 if re.search(r'\(\d+\)', fn) else 0
        length = len(fn)
        return (has_paren, length, fn)
    
    sorted_files = sorted(files, key=rank_key)
    return sorted_files[0]

def _worker_hash_file(f_path, f):
    """🌟 マルチスレッド用 MD5ハッシュ計算ワーカー"""
    try:
        if os.path.isfile(f_path):
            with open(f_path, "rb") as file_to_hash:
                file_hash = hashlib.md5(file_to_hash.read()).hexdigest()
            return f, file_hash
    except: pass
    return f, None

def compact_and_reindex_master_assets(chat_folder, raw_filepath):
    """
    基準マスターアセットの重複排除（カッコなし名を最優先保存）および
    1からの数値順連番（asset_1.png〜）への自動再インデックス化をマルチスレッド高速処理で行います。
    """
    assets_dir = os.path.join(chat_folder, "assets")
    if not os.path.exists(assets_dir) or not os.path.exists(raw_filepath):
        return 0, 0, 0

    all_files = sorted(os.listdir(assets_dir))
    original_assets_count = len(all_files)

    # 1. 🌟 MD5指紋比較による重複グループ化 (マルチスレッド一斉並列計算)
    hashes = {}
    file_tasks = [(os.path.join(assets_dir, f), f) for f in all_files]

    if file_tasks:
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_worker_hash_file, f_path, f) for f_path, f in file_tasks]
            for future in as_completed(futures):
                f, file_hash = future.result()
                if file_hash:
                    hashes.setdefault(file_hash, []).append(f)

    obsolete_to_survivor = {}
    removed_count = 0

    # 🌟 重複処理：カッコなしのシンプル名を生き残りに選ぶ！
    for file_hash, files in hashes.items():
        if len(files) > 1:
            survivor = select_best_survivor(files)
            for obsolete in files:
                if obsolete != survivor:
                    obsolete_to_survivor[obsolete] = survivor
                    try: 
                        os.remove(os.path.join(assets_dir, obsolete))
                        removed_count += 1
                    except: pass

    # 2. Markdownファイルの読み込み＆パス書き換え
    try:
        with open(raw_filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return removed_count, 0, original_assets_count

    for obsolete, survivor in obsolete_to_survivor.items():
        content = content.replace(f"./assets/{obsolete}", f"./assets/{survivor}")

    # 3. 隙間を詰めるための自動再リインデックス連番化
    def get_asset_num(filename):
        m = re.search(r'asset_(\d+)', filename)
        return int(m.group(1)) if m else 999999
    surviving_files = sorted(os.listdir(assets_dir), key=get_asset_num)

    temp_names = []
    for idx, f in enumerate(surviving_files):
        f_path = os.path.join(assets_dir, f)
        ext = f.split(".")[-1]
        temp_name = f"temp_{idx}.{ext}"
        try:
            os.rename(f_path, os.path.join(assets_dir, temp_name))
            temp_names.append((f, temp_name, ext))
        except: pass

    for idx, (original_name, temp_name, ext) in enumerate(temp_names):
        new_name = f"asset_{idx + 1}.{ext}"
        try:
            os.rename(os.path.join(assets_dir, temp_name), os.path.join(assets_dir, new_name))
            content = content.replace(f"./assets/{original_name}", f"./assets/{new_name}")
        except: pass

    try:
        with open(raw_filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except: pass

    return removed_count, len(surviving_files), original_assets_count

def process_inline_and_local_assets(turn_parts, assets_folder_path, asset_counter):
    """
    発言ターン内の Base64 インラインデータを復元し、
    assets フォルダ内へ asset_X.ext として物理保存します。
    """
    os.makedirs(assets_folder_path, exist_ok=True)
    part_text = ""

    for part in turn_parts:
        if isinstance(part, dict):
            if "text" in part:
                part_text += part["text"] + "\n"
            elif "inlineData" in part or "inlineImage" in part:
                inline = part.get("inlineData", part.get("inlineImage"))
                if isinstance(inline, dict):
                    mime = inline.get("mimeType", "")
                    b64_data = inline.get("data", "")
                    if b64_data:
                        if "," in b64_data:
                            b64_data = b64_data.split(",")[1]
                        try:
                            decoded_data = base64.b64decode(b64_data)
                            ext, _ = detect_file_type(decoded_data)
                            if not ext:
                                if "image/" in mime: ext = "png"
                                elif "audio/" in mime: ext = "mp3"
                                elif "video/" in mime: ext = "mp4"
                                else: ext = "bin"

                            if ext:
                                asset_filename = f"asset_{asset_counter}.{ext}"
                                asset_filepath = os.path.join(assets_folder_path, asset_filename)
                                with open(asset_filepath, "wb") as img_f:
                                    img_f.write(decoded_data)

                                part_text += f"\n![添付メディア](./assets/{asset_filename})\n"
                                asset_counter += 1
                        except: pass

    return part_text, asset_counter

def _worker_copy_salvage(src_s_path, dst_s_path):
    """🌟 マルチスレッド用 迷子アセットコピーワーカー"""
    try:
        if os.path.exists(src_s_path):
            shutil.copy2(src_s_path, dst_s_path)
            return True, src_s_path
    except: pass
    return False, None

def salvage_unlinked_assets(src_dir, target_save_dir, stray_assets, source_op="copy", service_name="Google AI Studio"):
    """
    どのチャットにも紐づかなかった迷子アセットを
    __unlinked_salvage フォルダへ安全に移送・救出します (マルチスレッド並列コピー対応)。
    """
    if not stray_assets or not os.path.exists(src_dir):
        return 0, set()

    salvage_dir = os.path.join(target_save_dir, service_name, "__unlinked_salvage")
    os.makedirs(salvage_dir, exist_ok=True)

    processed_source_files = set()
    salvaged_count = 0

    copy_tasks = [(os.path.join(src_dir, s_file), os.path.join(salvage_dir, s_file)) for s_file in stray_assets]

    if copy_tasks:
        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_worker_copy_salvage, sp, dp) for sp, dp in copy_tasks]
            for future in as_completed(futures):
                ok, src_p = future.result()
                if ok:
                    salvaged_count += 1
                    if source_op == "cut" and src_p:
                        processed_source_files.add(src_p)

    return salvaged_count, processed_source_files