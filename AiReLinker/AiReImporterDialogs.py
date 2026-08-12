# -*- coding: utf-8 -*-
# AiReImporterDialogs.py - マークダウン統合レポート表示・データ直結スリムリスト・別窓ダイアログモジュール (完全版)
import os
import sys
import shutil
import re
import tkinter as tk
from tkinter import ttk, messagebox

def render_chat_markdown(text_widget, raw_text, show_rich=True):
    """💬 チャット会話ログ専用のマークダウン装飾レンダラー（USER / MODEL マーク付き）"""
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)

    if not raw_text:
        text_widget.insert(tk.END, "⚠️ プレビュー表示する本文データがありません。")
        return

    if not show_rich:
        text_widget.insert(tk.END, raw_text)
        return

    text_widget.tag_config("h1", font=("MS Gothic", 13, "bold"), foreground="#1a73e8", spacing1=8)
    text_widget.tag_config("h2", font=("MS Gothic", 11, "bold"), foreground="#2ea44f", spacing1=6)
    text_widget.tag_config("h3", font=("MS Gothic", 10, "bold"), foreground="#e67e22", spacing1=4)
    text_widget.tag_config("bold", font=("MS Gothic", 9, "bold"))
    text_widget.tag_config("quote", font=("MS Gothic", 9, "italic"), foreground="#666666", background="#f0f0f0", lmargin1=15, lmargin2=15)
    text_widget.tag_config("user_header", font=("MS Gothic", 9, "bold"), foreground="#1a73e8", spacing1=10)
    text_widget.tag_config("model_header", font=("MS Gothic", 9, "bold"), foreground="#2ea44f", spacing1=10)

    lines = raw_text.split("\n")
    start_line = 0
    yaml_bounds = []
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            yaml_bounds.append(idx)
            if len(yaml_bounds) == 2:
                break
    if len(yaml_bounds) == 2:
        start_line = yaml_bounds[1] + 1

    for line in lines[start_line:]:
        line_upper = line.upper()
        if "👤" in line or "USER" in line_upper or "あなた" in line_upper:
            text_widget.insert(tk.END, "\n👤 USER:\n", "user_header")
            continue
        elif "🤖" in line or "MODEL" in line_upper or "AI" in line_upper:
            text_widget.insert(tk.END, "\n🤖 MODEL:\n", "model_header")
            continue

        if line.startswith("# "):
            text_widget.insert(tk.END, line[2:] + "\n", "h1")
        elif line.startswith("## "):
            text_widget.insert(tk.END, line[3:] + "\n", "h2")
        elif line.startswith("### "):
            text_widget.insert(tk.END, line[4:] + "\n", "h3")
        elif line.startswith("> "):
            text_widget.insert(tk.END, line[2:] + "\n", "quote")
        elif "**" in line:
            parts = line.split("**")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    text_widget.insert(tk.END, part, "bold")
                else:
                    text_widget.insert(tk.END, part)
            text_widget.insert(tk.END, "\n")
        else:
            text_widget.insert(tk.END, line + "\n")

def render_clean_report_markdown(text_widget, raw_text, show_rich=True):
    """📊 診断レポート専用クリーン描画エンジン（対話マークなし）"""
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)

    if not show_rich:
        text_widget.insert(tk.END, raw_text)
        return

    text_widget.tag_config("h1", font=("MS Gothic", 13, "bold"), foreground="#2c3e50", spacing1=8)
    text_widget.tag_config("h2", font=("MS Gothic", 11, "bold"), foreground="#16a085", spacing1=6)
    text_widget.tag_config("h3", font=("MS Gothic", 10, "bold"), foreground="#d35400", spacing1=4)
    text_widget.tag_config("bold", font=("MS Gothic", 9, "bold"))
    text_widget.tag_config("quote", font=("MS Gothic", 9, "italic"), foreground="#555555", background="#f8f9fa", lmargin1=15, lmargin2=15)
    text_widget.tag_config("suggest", font=("MS Gothic", 9, "bold"), foreground="#c0392b", background="#fef9e7")

    lines = raw_text.split("\n")
    start_line = 0
    yaml_bounds = []
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            yaml_bounds.append(idx)
            if len(yaml_bounds) == 2:
                break
    if len(yaml_bounds) == 2:
        start_line = yaml_bounds[1] + 1

    for line in lines[start_line:]:
        if "💡 救出候補:" in line:
            text_widget.insert(tk.END, line + "\n", "suggest")
        elif line.startswith("# "):
            text_widget.insert(tk.END, line[2:] + "\n", "h1")
        elif line.startswith("## "):
            text_widget.insert(tk.END, line[3:] + "\n", "h2")
        elif line.startswith("### "):
            text_widget.insert(tk.END, line[4:] + "\n", "h3")
        elif line.startswith("> "):
            text_widget.insert(tk.END, line[2:] + "\n", "quote")
        elif "**" in line:
            parts = line.split("**")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    text_widget.insert(tk.END, part, "bold")
                else:
                    text_widget.insert(tk.END, part)
            text_widget.insert(tk.END, "\n")
        else:
            text_widget.insert(tk.END, line + "\n")

def show_chat_preview_dialog(parent, chat_item, apply_icon_func=None):
    """ダブルクリックで起動する独立プレビュー先読みウィンドウ"""
    title = chat_item.get("title", "プレビュー")
    top_win = parent.winfo_toplevel()
    prev_win = tk.Toplevel(top_win)
    prev_win.title(f"📖 プレビュー先読み - 『{title}』")
    prev_win.geometry("750x600")

    if apply_icon_func: apply_icon_func(prev_win)

    header_f = ttk.Frame(prev_win, padding=5)
    header_f.pack(fill="x", side="top")
    ttk.Label(header_f, text=f"💬 プレビュー: {title}", font=("MS Gothic", 9, "bold")).pack(side="left", padx=5)

    var_rich = tk.BooleanVar(value=True)

    preview_text_str = ""
    if hasattr(parent, 'last_rendered_chat_md') and parent.last_rendered_chat_md:
        preview_text_str = parent.last_rendered_chat_md
    else:
        raw_preview_md = ["---", f"title: \"{title}\"", f"service: \"{chat_item.get('service', '不明')}\"", "---"]
        for turn in chat_item.get("parsed_contents", []):
            role = turn.get("role", "unknown")
            disp_role = "👤 USER" if role == "user" else "🤖 MODEL"
            parts = turn.get("parts", [])
            part_text = ""
            for p in parts:
                if isinstance(p, dict) and "text" in p:
                    part_text += p["text"] + "\n"
            if part_text.strip():
                raw_preview_md.append(f"### {disp_role}\n{part_text.strip()}\n")

        preview_text_str = "\n".join(raw_preview_md)

    if not preview_text_str.strip():
        preview_text_str = f"# {title}\n\n" + chat_item.get("raw_text_data", "")

    def switch_rich_mode():
        render_chat_markdown(txt_box, preview_text_str, var_rich.get())
        txt_box.config(state="disabled")

    chk_rich = ttk.Checkbutton(header_f, text="マークダウン装飾を適用する", variable=var_rich, command=switch_rich_mode)
    chk_rich.pack(side="right", padx=10)

    ysb_prev = ttk.Scrollbar(prev_win)
    ysb_prev.pack(fill="y", side="right")

    txt_box = tk.Text(prev_win, background="#ffffff", wrap="word", yscrollcommand=ysb_prev.set)
    txt_box.pack(fill="both", expand=True, side="left", padx=5, pady=5)
    ysb_prev.config(command=txt_box.yview)

    switch_rich_mode()

def show_report_popout_window(parent, title_tag, report_md_text, apply_icon_func=None):
    """診断レポートを『薄黄色シンプルリスト形式』で独立別窓へ拡大表示（数字付き/数字なし切替対応）"""
    top_win = parent.winfo_toplevel()
    pop_win = tk.Toplevel(top_win)
    pop_win.title(f"📊 診断レポート拡大表示 - 『{title_tag}』")
    pop_win.geometry("750x600")

    if apply_icon_func: apply_icon_func(pop_win)

    # 1. 上部ヘッダー
    header_f = ttk.Frame(pop_win, padding=5)
    header_f.pack(fill="x", side="top")
    ttk.Label(header_f, text=f"📊 スリムリスト表示: {title_tag}", font=("MS Gothic", 10, "bold")).pack(side="left", padx=5)

    var_show_num = tk.BooleanVar(value=True)

    # 全文コピー処理
    def do_copy():
        try:
            parent.clipboard_clear()
            parent.clipboard_append(txt_box.get("1.0", tk.END).strip())
            messagebox.showinfo("コピー完了", f"『{title_tag}』のテキスト全文をクリップボードにコピーしました！")
        except: pass

    btn_copy = ttk.Button(header_f, text="📋 全文コピー", command=do_copy)
    btn_copy.pack(side="right", padx=5)

    chk_num = ttk.Checkbutton(header_f, text="連番数字(001.等)を付ける", variable=var_show_num, command=lambda: rebuild_text_list())
    chk_num.pack(side="right", padx=10)

    # 2. 右側スクロールバー
    ysb = ttk.Scrollbar(pop_win)
    ysb.pack(fill="y", side="right")

    # 3. テキストボックス
    txt_box = tk.Text(
        pop_win, 
        background="#fcf8e3", 
        fg="#8a6d3b", 
        font=("MS Gothic", 10), 
        wrap="word",
        yscrollcommand=ysb.set
    )
    txt_box.pack(fill="both", expand=True, side="left", padx=8, pady=8)
    ysb.config(command=txt_box.yview)

    # 4. 数字あり/なし動的切り替え描画関数
    def rebuild_text_list():
        pure_items = []

        if "検出チャット" in title_tag and hasattr(parent, 'scanned_chats_data'):
            pure_items = [item.get("title", "無題") for item in parent.scanned_chats_data if item.get("title")]
        elif "紐づけ成功" in title_tag and hasattr(parent, 'last_linked_assets'):
            pure_items = sorted(list(parent.last_linked_assets))
        elif "迷子" in title_tag and hasattr(parent, 'last_missing_assets'):
            pure_items = sorted(parent.last_missing_assets)
        elif "重複" in title_tag and hasattr(parent, 'last_duplicate_map'):
            dup_set = set()
            for f_hash, files in parent.last_duplicate_map.items():
                if len(files) > 1:
                    def rank_key(fn):
                        has_p = 1 if re.search(r'\(\d+\)', fn) else 0
                        return (has_p, len(fn), fn)
                    sorted_f = sorted(files, key=rank_key)
                    for obsolete in sorted_f[1:]:
                        dup_set.add(obsolete)
            pure_items = sorted(list(dup_set))
        elif ("Missing" in title_tag or "行方不明" in title_tag) and hasattr(parent, 'last_missing_links'):
            seen = set()
            for m in parent.last_missing_links:
                fn = m.get("file")
                if fn and fn not in seen:
                    seen.add(fn)
                    pure_items.append(fn)

        clean_lines = [
            "="*50,
            f" 📊 {title_tag} 一覧 ({len(pure_items)} 件)",
            "="*50
        ]

        show_num = var_show_num.get()
        if pure_items:
            for idx, item_str in enumerate(pure_items):
                if show_num:
                    clean_lines.append(f"{idx+1:03d}. {item_str}")
                else:
                    clean_lines.append(f"{item_str}")
        else:
            clean_lines.append("\n※ 該当するデータが見つからないか、未解析状態です。")

        txt_box.delete("1.0", tk.END)
        txt_box.insert(tk.END, "\n".join(clean_lines))

    rebuild_text_list()

def show_report_in_main_preview(ui, title_tag, report_md_text):
    """別窓を出さず、メインのプレビュー枠へレポートを直接描画"""
    ui.current_view_state = "report"
    ui.current_report_type = title_tag
    ui.last_rendered_report_md = report_md_text

    render_clean_report_markdown(ui.preview_text, report_md_text, ui.var_rich_preview.get())
    ui.preview_text.config(state="disabled")
    ui.set_report_button_state(True)
    ui.log(f"📖 プレビューエリアに『{title_tag}』の診断レポートを出力しました。")

def show_single_chat_detail_report(ui, chat_item, detail_type):
    """個別チャットの「成功 / 重複 / Missing」セルクリック時の単体詳細レポート描画関数"""
    title = chat_item.get("title", "無題")
    matched = chat_item.get("matched_assets", [])

    md = [
        "---",
        f"title: \"💬 『{title}』 - {detail_type} 詳細レポート\"",
        "---",
        f"# 💬 チャット: 『{title}』\n",
        f"## 【{detail_type} アセット一覧】\n"
    ]

    if detail_type == "成功":
        if matched:
            for idx, fn in enumerate(matched):
                md.append(f"{idx+1:03d}. `{fn}`")
        else:
            md.append("> このチャットで紐づけ成功したアセットはありません。")

    elif detail_type == "重複":
        dup_set = set()
        for f_hash, files in ui.last_duplicate_map.items():
            if len(files) > 1:
                for f in files[1:]: dup_set.add(f)
        chat_dups = [m for m in matched if m in dup_set]
        if chat_dups:
            for idx, fn in enumerate(chat_dups):
                md.append(f"{idx+1:03d}. ❌ [重複] `{fn}`")
        else:
            md.append("> 🎉 このチャット内に重複しているアセットはありません。")

    elif detail_type == "Missing":
        chat_missing = [m.get("file") for m in ui.last_missing_links if m.get("chat") == title]
        if chat_missing:
            for idx, fn in enumerate(chat_missing):
                md.append(f"{idx+1:03d}. `{fn}`")
        else:
            md.append("> 🎉 このチャット内に行方不明(Missing)のアセット参照はありません！（完全整合）")

    show_report_in_main_preview(ui, f"個別:{title}({detail_type})", "\n".join(md))

# 📂 総ファイル数レポート
def show_all_files_report(ui):
    src = ui.src_dir_var.get().strip()
    if not src or not os.path.exists(src): return
    all_files = sorted(os.listdir(src))

    md = [
        "---",
        "title: \"📂 インポート元フォルダ内 ファイル一覧\"",
        f"total_count: {len(all_files)}",
        "---",
        f"# 📂 インポート元フォルダ全ファイル ({len(all_files)} 件)\n",
        f"> **参照パス:** `{src}`\n"
    ]
    for idx, f in enumerate(all_files):
        md.append(f"{idx+1:03d}. `{f}`")

    show_report_in_main_preview(ui, "総ファイル数", "\n".join(md))

# 💬 検出チャット一覧レポート
def show_detected_chats_report(ui):
    scanned = ui.scanned_chats_data
    md = [
        "---",
        "title: \"💬 検出チャット一覧診断レポート\"",
        f"chat_count: {len(scanned)}",
        "---",
        f"# 💬 検出されたAI会話ログ一覧 ({len(scanned)} 件)\n"
    ]
    if scanned:
        for idx, item in enumerate(scanned):
            md.append(f"### {idx+1:02d}. 『{item.get('title', '無題')}』")
            md.append(f"* **サービス:** {item.get('service', '不明')}")
            md.append(f"* **ファイル名:** `{item.get('file_name', '不明')}`")
            md.append(f"* **更新日時:** {item.get('end_time', '不明')}\n")
    else:
        md.append("> ⚠️ 検出されたチャットログはありません。『スキャン開始』を実行してください。")

    show_report_in_main_preview(ui, "検出チャット", "\n".join(md))

# 🖼️ 紐づけ成功アセット一覧レポート
def show_linked_assets_report(ui):
    md = [
        "---",
        "title: \"🖼️ 紐づけ成功アセット一覧レポート\"",
        f"linked_count: {len(ui.last_linked_assets)}",
        "---",
        f"# 🖼️ 照合・紐づけ成功アセット ({len(ui.last_linked_assets)} 件)\n"
    ]

    if ui.is_analyzed and ui.last_linked_assets:
        for idx, chat_item in enumerate(ui.scanned_chats_data):
            matched = chat_item.get("matched_assets", [])
            if matched:
                md.append(f"### 💬 チャット #{idx+1:02d}: 『{chat_item.get('title', '無題')}』 ({len(matched)} 件)")
                for fn in matched:
                    md.append(f"* `{fn}`")
                md.append("")
    elif not ui.is_analyzed:
        md.append("> ⌛ 『🧬 アセット詳細解析』ボタンを押して解析を実行してください（未解析状態です）。")
    else:
        md.append("> 紐づいたアセットはありません。")

    show_report_in_main_preview(ui, "紐づけ成功アセット", "\n".join(md))

# ❓ 迷子アセット一覧レポート
def show_missing_assets_report(ui):
    stray = sorted(ui.last_missing_assets)
    md = [
        "---",
        "title: \"❓ 迷子アセット一覧診断レポート\"",
        f"stray_count: {len(stray)}",
        "---",
        f"# ❓ 迷子アセット一覧 ({len(stray)} 件)\n",
        "> どのチャット本文・JSONからも参照されなかったフリーのアセットファイル群です。\n"
    ]
    if ui.is_analyzed and stray:
        for idx, fn in enumerate(stray):
            md.append(f"{idx+1:03d}. `{fn}`")
    elif not ui.is_analyzed:
        md.append("> ⌛ 『🧬 アセット詳細解析』ボタンを押して解析を実行してください（未解析状態です）。")
    else:
        md.append("> 🎉 迷子アセットは検出されませんでした！（100% 紐づいています）")

    show_report_in_main_preview(ui, "迷子アセット", "\n".join(md))

# ⚛️ 重複アセット一覧レポート
def show_duplicate_assets_report(ui):
    dup_map = ui.last_duplicate_map
    total_dup = sum(len(files) - 1 for files in dup_map.values() if len(files) > 1) if ui.is_analyzed else 0

    md = [
        "---",
        "title: \"⚛️ 重複アセット一覧診断レポート\"",
        f"duplicate_count: {total_dup}",
        "---",
        f"# ⚛️ 重複アセット診断 ({total_dup} 件の不要ダブりを検出)\n",
        "> **生き残り（正・代表）ルール:** カッコ `(1)` が付いていない最もシンプルで綺麗な名前を最優先で代表保存します。\n"
    ]
    if ui.is_analyzed and dup_map and total_dup > 0:
        grp_idx = 1
        for f_hash, files in dup_map.items():
            if len(files) > 1:
                def rank_key(fn):
                    has_p = 1 if re.search(r'\(\d+\)', fn) else 0
                    return (has_p, len(fn), fn)
                sorted_f = sorted(files, key=rank_key)
                survivor = sorted_f[0]

                md.append(f"### グループ #{grp_idx:02d} (👑 代表保存: `{survivor}`)")
                for obsolete in sorted_f[1:]:
                    md.append(f"* ❌ [削除対象] `{obsolete}`")
                md.append("")
                grp_idx += 1
    elif not ui.is_analyzed:
        md.append("> ⌛ 『🧬 アセット詳細解析』ボタンを押して解析を実行してください（未解析状態です）。")
    else:
        md.append("> 🎉 重複しているアセットファイルはありません！")

    show_report_in_main_preview(ui, "重複アセット", "\n".join(md))

# ❌ 行方不明(Missing)一覧レポート
def show_missing_links_report(ui):
    missing_links = ui.last_missing_links
    stray_files = ui.last_missing_assets

    md = [
        "---",
        "title: \"❌ 行方不明(Missing) アセット一覧診断レポート\"",
        f"missing_count: {len(missing_links) if ui.is_analyzed else 0}",
        "---",
        f"# ❌ 行方不明(Missing) 参照一覧 ({len(missing_links) if ui.is_analyzed else 0} 件)\n",
        "> チャット本文内で指定されているが、フォルダ内に実体が見つからない欠損参照ファイルです。\n"
    ]

    if ui.is_analyzed and missing_links:
        chats_missing_map = {}
        for item in missing_links:
            fn = item.get("file", "")
            c_title = item.get("chat", "不明")
            chats_missing_map.setdefault(c_title, []).append(fn)

        grp_i = 1
        for c_title, f_list in chats_missing_map.items():
            md.append(f"### 💬 チャット #{grp_i:02d}: 『{c_title}』 ({len(f_list)} 件の欠損)")
            for m_fn in f_list:
                md.append(f"* `{m_fn}`")

                clean_missing = re.sub(r'[\(\)\d_]+', '', m_fn).lower()
                suggested = []
                for sf in stray_files:
                    clean_stray = re.sub(r'[\(\)\d_]+', '', sf).lower()
                    if clean_missing and clean_missing in clean_stray:
                        suggested.append(sf)

                if suggested:
                    md.append(f"  └─ 💡 救出候補: 迷子アセット内に類似ファイル `{suggested[0]}` が存在します！")
            md.append("")
            grp_i += 1

    elif not ui.is_analyzed:
        md.append("> ⌛ 『🧬 アセット詳細解析』ボタンを押して解析を実行してください（未解析状態です）。")
    else:
        md.append("> 🎉 行方不明(Missing)の参照ファイルは検出されませんでした！（完全整合）")

    show_report_in_main_preview(ui, "行方不明(Missing)", "\n".join(md))

def show_help_dialog(parent, apply_icon_func=None):
    top_win = parent.winfo_toplevel()
    dlg = tk.Toplevel(top_win)
    dlg.title("📖 AiReLinkerImporter 操作ガイド")
    dlg.geometry("650x500")

    if apply_icon_func: apply_icon_func(dlg)

    ttk.Label(dlg, text="📖 AiReLinkerImporter 操作ガイド", font=("MS Gothic", 11, "bold")).pack(pady=8, padx=10, anchor="w")
    txt_frame = ttk.Frame(dlg, padding=10)
    txt_frame.pack(fill="both", expand=True)

    ysb_help = ttk.Scrollbar(txt_frame)
    txt_box = tk.Text(txt_frame, width=60, height=20, background="#ffffff", font=("MS Gothic", 9), wrap="word", yscrollcommand=ysb_help.set)
    ysb_help.config(command=txt_box.yview)

    txt_box.grid(row=0, column=0, sticky="nsew")
    ysb_help.grid(row=0, column=1, sticky="ns")

    txt_frame.rowconfigure(0, weight=1)
    txt_frame.columnconfigure(0, weight=1)

    help_text = """
==================================================
 ⚓ AiReLinkerImporter - 使い方マニュアル
==================================================

【基本操作】
 1. 🔍 [スキャン開始]: フォルダ内のチャットを一括検出します。
 2. 🧬 [アセット詳細解析]: 全ファイルのアセット紐づき状態を深層診断します。
 3. 🔨 [インポート調停実行]: 選択したチャットをImporter専用領域へ保存します。
 4. 🔨 [アセット最適化を実行]: 重複削除と隙間ゼロ連番リネームを行います。

【別窓機能】
 • 📋 全文コピーボタン: ポチッと一発で画面上のテキスト全文をクリップボードへコピーします。
 • ☑ 連番数字のON/OFF: チェックを外すと、数字なしの純粋なファイル名/タイトルだけの羅列へ切り替わります。
==================================================
"""
    txt_box.insert(tk.END, help_text)
    txt_box.config(state="disabled")

def confirm_app_close(parent, current_dir):
    """🌟 終了確認 ＆ 一時フォルダ（__temp_gemini_split 等）の完全クレンジング消去"""
    src_dir = parent.src_dir_var.get().strip() if hasattr(parent, "src_dir_var") else ""
    
    temp_folders = ["__preview_linked_temp", "__preview_report_temp"]
    existing_temp_paths = []

    for folder_name in temp_folders:
        p = os.path.join(current_dir, folder_name)
        if os.path.exists(p) and os.path.isdir(p):
            existing_temp_paths.append(p)

    # インポート元フォルダ内の __temp_gemini_split も検出対象に指定！
    if src_dir and os.path.exists(src_dir):
        g_temp = os.path.join(src_dir, "__temp_gemini_split")
        if os.path.exists(g_temp) and os.path.isdir(g_temp):
            existing_temp_paths.append(g_temp)

    if not existing_temp_paths:
        try:
            top_win = parent.winfo_toplevel()
            top_win.destroy()
        except:
            sys.exit(0)
        return True

    # 🌟 クレンジング確認ダイアログの起動
    ans = messagebox.askyesnocancel(
        "終了確認",
        "一括インポート作業を終了します。\n\n作業用に一時作成されたフォルダ（__temp_gemini_split 等）を完全消去して元の綺麗な状態に戻しますか？"
    )
    if ans is None: return False

    if ans:
        for p in existing_temp_paths:
            try: shutil.rmtree(p)
            except: pass

    try:
        top_win = parent.winfo_toplevel()
        top_win.destroy()
    except:
        sys.exit(0)
    return True