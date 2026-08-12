# -*- coding: utf-8 -*-
# AiReAccessway.pyw - AI実行ハブ ＆ オーケストレーター (3大要約アルゴリズムモード切替対応版)
import os
import sys
import json
import time
import re
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox

# 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico")

# AiReAPI モジュールの統合ロード
try:
    from AiReAPI import AiReAPIController, AiReAPIFrame
    HAS_API_MODULE = True
except ImportError:
    HAS_API_MODULE = False

try:
    import ctypes
    myappid = 'airelinker.suite.accessway.v16'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

# デフォルトプロンプト定義
DEFAULT_PROMPT_SUMMARY = """【指示】以下の対話ログの主要な目的、議論されたテーマ、最終的な結論・成果を、会話のスケール（長さ）に応じた適切な文章量と密度で分かりやすく整理してください。"""

DEFAULT_PROMPT_STORY = """【指示】以下の対話ログから、ユーザーが何を目指し、どのようなエラー・勘違い・失敗の足踏み（ループ）に遭遇し、最終的にどう解決したか（または未解決か）の試行錯誤の経緯・プロセスを時系列で客観的に抽出してください。最初から順調だったような綺麗なまとめは避けてください。"""

DEFAULT_PROMPT_TAGS = """【指示】以下の対話ログの主要なトピックを表すキーワード（タグ）を3〜5個（重要な場合は最大10個程度）抽出してください。
出力形式: カンマ区切りのテキストのみ（例: Python, Tkinter, バグ修正）"""

DEFAULT_PROMPT_FORGE_FULL = """【指示】以下の複数の対話ログを総合・整理し、全体で話し合われた主要な目的、仕様、結論、成果物を1本の分かりやすいマークダウンにまとめ直してください。"""

DEFAULT_PROMPT_FORGE_TOPIC = """【指示】以下の複数の対話ログの中から、指定トピックに関連するやり取り・発言・仕様部分だけをピンポイントで抽出し、1本に整理統合してください。"""

DEFAULT_PROMPT_FORGE_STORY = """【指示】以下の複数の対話ログから、どのような試行錯誤、エラー、勘違いの足踏みが発生し、どのように解決に至ったかのプロセスを時系列で客観的に抽出しマージしてください。"""

DEFAULT_PROMPT_FORGE_C1_LABEL = "💻 完成コード一括抽出"
DEFAULT_PROMPT_FORGE_C1_PROMPT = """【指示】以下の複数の対話ログから、試行錯誤の過程は一切省き、最終的に完成・決定したソースコードおよび設定仕様のみを綺麗に抽出・統合してください。"""

DEFAULT_PROMPT_FORGE_C2_LABEL = "📝 仕様書・設計書作成"
DEFAULT_PROMPT_FORGE_C2_PROMPT = """【指示】以下の複数の対話ログから、決定したシステム仕様、データ構造、UIデザイン方針を網羅した技術仕様書ドキュメントを作成してください。"""

# デフォルト対話ペルソナ定義
DEFAULT_PERSONAS = [
    {
        "id": "standard",
        "name": "標準アシスタント",
        "system_prompt": "あなたは親切で優秀なAIアシスタントです。ユーザーの質問に対して明確で分かりやすく、正確な回答を日本語で提供してください。"
    },
    {
        "id": "tech_advisor",
        "name": "専門技術顧問・エンジニア",
        "system_prompt": "あなたは経験豊富なシニアソフトウェアエンジニアおよび技術顧問です。ソースコード、アーキテクチャ、バグ修正に関して論理的かつ厳格で詳細な解説を提供してください。"
    },
    {
        "id": "kansai_chara",
        "name": "関西弁アシスタント",
        "system_prompt": "あなたは明るくフレンドリーな関西弁のAIパートナーです。親しみやすい関西弁（〜やで、〜やねん、〜知らんけど等）で楽しく的確に回答してください。"
    }
]

# 4段階スケールデフォルト定義 (小・中・大・超極大)
DEFAULT_SCALE_SMALL_CHARS = 50000
DEFAULT_SCALE_SMALL_DELAY = 4.5

DEFAULT_SCALE_MEDIUM_CHARS = 200000
DEFAULT_SCALE_MEDIUM_DELAY = 15.0

DEFAULT_SCALE_LARGE_CHARS = 500000
DEFAULT_SCALE_LARGE_DELAY = 30.0

DEFAULT_SCALE_HUGE_CHARS = 1000000
DEFAULT_SCALE_HUGE_DELAY = 60.0


class AiReAccesswayController:
    """🌟 全モジュールからのAI処理要求を一括受託・管理・実行するオーケストレーター"""
    def __init__(self, config, save_dir=None):
        self.config = config
        self.save_dir = save_dir if save_dir else os.path.join(CURRENT_DIR, "logs")
        if HAS_API_MODULE:
            self.api_controller = AiReAPIController(config)
        else:
            self.api_controller = None

    def should_update_summary(self, chat_folder_path, raw_filepath):
        if self.config.get("trig_manual_only", False):
            return False, "完全手動更新モードのためスキップ"

        sum_filepath = os.path.join(chat_folder_path, f"summary_{os.path.basename(chat_folder_path)}.md")
        if not os.path.exists(sum_filepath) or not os.path.exists(raw_filepath):
            return True, "要約ファイルが未作成のため実行"

        try:
            with open(raw_filepath, "r", encoding="utf-8") as f: raw_text = f.read()
            with open(sum_filepath, "r", encoding="utf-8") as f: sum_text = f.read()

            raw_turns = raw_text.count("### ")
            
            last_turns = 0
            m = re.search(r'processed_turns:\s*(\d+)', sum_text)
            if m: last_turns = int(m.group(1))

            diff_turns = raw_turns - last_turns
            
            if self.config.get("trig_turns_enabled", True):
                min_diff = self.config.get("diff_min_turns", 10)
                if diff_turns >= min_diff:
                    return True, f"会話の差分ターン数達成分 ({diff_turns} >= {min_diff})"

            if self.config.get("trig_days_enabled", False):
                min_days = self.config.get("trig_min_days", 7)
                mtime = os.path.getmtime(sum_filepath)
                elapsed_days = (time.time() - mtime) / 86400.0
                if elapsed_days >= min_days and diff_turns > 0:
                    return True, f"経過日数条件達成 ({elapsed_days:.1f}日 >= {min_days}日)"

            return False, f"自動更新条件未達成のためスキップ (追加: {diff_turns} ターン)"

        except Exception as e:
            return True, f"判定例外のため念のため実行: {e}"

    def get_dynamic_scale_delay(self, text_length):
        enable_smart = self.config.get("enable_smart_delay", True)
        base_delay = self.config.get("delay_seconds", 4.5)

        if not enable_smart:
            return base_delay

        small_chars = self.config.get("scale_small_chars", DEFAULT_SCALE_SMALL_CHARS)
        small_delay = self.config.get("scale_small_delay", DEFAULT_SCALE_SMALL_DELAY)

        medium_chars = self.config.get("scale_medium_chars", DEFAULT_SCALE_MEDIUM_CHARS)
        medium_delay = self.config.get("scale_medium_delay", DEFAULT_SCALE_MEDIUM_DELAY)

        large_chars = self.config.get("scale_large_chars", DEFAULT_SCALE_LARGE_CHARS)
        large_delay = self.config.get("scale_large_delay", DEFAULT_SCALE_LARGE_DELAY)

        huge_delay = self.config.get("scale_huge_delay", DEFAULT_SCALE_HUGE_DELAY)

        if text_length <= small_chars:
            return max(base_delay, small_delay)
        elif text_length <= medium_chars:
            return max(base_delay, medium_delay)
        elif text_length <= large_chars:
            return max(base_delay, large_delay)
        else:
            return max(base_delay, huge_delay)

    def execute_request_with_cooldown_retry(self, prompt, task_type="summary", log_callback=None):
        enable_cooldown = self.config.get("enable_cooldown_retry", True)
        max_retries = 3 if enable_cooldown else 1

        for attempt in range(max_retries):
            ok, res = self.api_controller.send_request(prompt, task_type=task_type, log_callback=log_callback)
            if ok:
                return True, res

            if "429" in str(res) or "Too Many Requests" in str(res) or "Quota" in str(res):
                if attempt < max_retries - 1:
                    cooldown_sec = self.config.get("cooldown_seconds", 60)
                    if log_callback and callable(log_callback):
                        log_callback(f"  └─ ⚠️ 429 レート制限を検知。{cooldown_sec}秒間自動冷却待機してリトライします ({attempt+1}/{max_retries})...")
                    time.sleep(cooldown_sec)
                    continue

            return False, res

        return False, "リトライ上限に達しました。"

    def send_request_with_chunking(self, prompt, raw_content, max_chars, task_type="summary", log_callback=None):
        enable_chunking = self.config.get("enable_text_chunking", True)
        total_len = len(raw_content)

        if total_len <= max_chars or not enable_chunking:
            return self.execute_request_with_cooldown_retry(f"{prompt}\n\n【対話ログ】\n{raw_content[:max_chars]}", task_type=task_type, log_callback=log_callback)

        chunks = [raw_content[i:i + max_chars] for i in range(0, total_len, max_chars)]
        total_chunks = len(chunks)

        if log_callback and callable(log_callback):
            log_callback(f"  └─ ✂️ 長大ログ検出 (全 {total_len:,} 文字): {total_chunks} パートに分割して段階AI要約を開始...")

        chunk_summaries = []

        for idx, ch in enumerate(chunks):
            processed_chars = min((idx + 1) * max_chars, total_len)
            pct = int((processed_chars / total_len) * 100)
            
            progress_msg = f"全 {total_len:,} 文字中 {processed_chars:,} 文字完了 ({pct}%) [パート {idx+1}/{total_chunks}]"

            if log_callback and callable(log_callback):
                log_callback(f"  └─ 🔄 {progress_msg} をAI処理中 ({len(ch):,}文字)...")

            chunk_prompt = f"{prompt}\n\n【対話ログ パート {idx+1}/{total_chunks}】\n{ch}"
            ok, res = self.execute_request_with_cooldown_retry(chunk_prompt, task_type=task_type, log_callback=log_callback)

            if ok and res.strip():
                chunk_summaries.append(f"【パート {idx+1} 要約】\n{res.strip()}")
            else:
                if log_callback and callable(log_callback):
                    log_callback(f"  └─ ⚠️ パート {idx+1} の処理で警告発生: スキップします")

            actual_delay = self.get_dynamic_scale_delay(len(ch))
            time.sleep(actual_delay)

        if not chunk_summaries:
            return False, "全分割パートのAI処理に失敗しました。"

        if log_callback and callable(log_callback):
            log_callback("  └─ 🧩 各パートの要約結果を1本に統合合体中...")

        combined_summary_text = "\n\n".join(chunk_summaries)
        final_prompt = f"{prompt}\n\n【各パート要約一覧データ】\n{combined_summary_text}"
        return self.execute_request_with_cooldown_retry(final_prompt, task_type=task_type, log_callback=log_callback)

    def process_chat_summary_task(self, chat_folder_path, raw_filepath, log_callback=None):
        if not os.path.exists(raw_filepath) or not self.api_controller:
            return False, "rawファイルが存在しないか、APIモジュールが未ロードです。"

        try:
            with open(raw_filepath, "r", encoding="utf-8") as f: raw_content = f.read()
            raw_turns = raw_content.count("### ")
            
            # 🌟 要約アルゴリズムモード ("mode_22" / "mode_21" / "mode_42")
            summary_mode = self.config.get("summary_generation_mode", "mode_22")
            
            gen_sum = self.config.get("gen_enable_summary", True)
            gen_story = self.config.get("gen_enable_story", True)
            gen_tags = self.config.get("gen_enable_tags", True)

            p_sum = self.config.get("prompt_summary", DEFAULT_PROMPT_SUMMARY)
            p_story = self.config.get("prompt_story", DEFAULT_PROMPT_STORY)
            p_tags = self.config.get("prompt_tags", DEFAULT_PROMPT_TAGS)

            max_sum_chars = self.config.get("max_summary_text_length", 50000)
            max_tag_chars = self.config.get("max_tags_text_length", 10000)

            summary_result = ""
            story_result = ""
            extracted_tags = ["インポート"]

            # -----------------------------------------------------------------
            # 🌟 モード 1: mode_22 (新・推奨方式: 22回送信 - ストーリー主導2段階生成)
            # -----------------------------------------------------------------
            if summary_mode == "mode_22" and gen_sum and gen_story:
                if log_callback and callable(log_callback):
                    log_callback("  └─ 🚀 [新・22回モード] ① ストーリーを最優先で超濃密に抽出中...")

                # A. 100%出力枠を使って「ストーリー」のみを濃密スキャン
                ok_st, story_res = self.send_request_with_chunking(p_story, raw_content, max_sum_chars, task_type="summary", log_callback=log_callback)
                if ok_st: story_result = story_res.strip()

                # B. できあがった濃密ストーリーから1回で「概要」を生成
                if story_result:
                    if log_callback and callable(log_callback):
                        log_callback("  └─ 📌 [新・22回モード] ② 完成ストーリーから概要(Short Summary)を一発抽出中...")

                    prompt_sum_from_story = (
                        f"{p_sum}\n\n"
                        f"【元となる決定版ストーリー資料】\n{story_result}"
                    )
                    ok_sm, sum_res = self.execute_request_with_cooldown_retry(prompt_sum_from_story, task_type="summary", log_callback=log_callback)
                    if ok_sm: summary_result = sum_res.strip()

            # -----------------------------------------------------------------
            # 🌟 モード 2: mode_21 (一括同時方式: 21回送信 - スピード最優先)
            # -----------------------------------------------------------------
            elif summary_mode == "mode_21" and gen_sum and gen_story:
                if log_callback and callable(log_callback):
                    log_callback("  └─ ⚡ [21回一括モード] 概要 ＆ ストーリーを同時抽出中...")

                combined_prompt = (
                    "【指示】以下の対話ログを読み込み、次の2つの項目を同時に抽出して出力してください。\n\n"
                    "■ 1. 概要 (Short Summary)\n"
                    f"{p_sum}\n\n"
                    "■ 2. 試行錯誤のストーリー・経過プロセス\n"
                    f"{p_story}\n\n"
                    "※出力時の注意: 必ず以下の見出しで区切って出力してください:\n"
                    "## 📌 概要 (Short Summary)\n"
                    "(概要内容)\n\n"
                    "## 📜 試行錯誤のストーリー・経過プロセス\n"
                    "(ストーリー内容)"
                )
                ok, res = self.send_request_with_chunking(combined_prompt, raw_content, max_sum_chars, task_type="summary", log_callback=log_callback)
                if ok and res.strip():
                    summary_result = res.strip() # 合体結果

            # -----------------------------------------------------------------
            # 🌟 モード 3: mode_42 (従来方式: 42回送信 - 個別2往復完全生成)
            # -----------------------------------------------------------------
            else:
                if gen_sum:
                    if log_callback and callable(log_callback): 
                        log_callback("  └─ 📌 [旧・42回モード] 概要（Short Summary）を独立AI生成中...")
                    ok, res = self.send_request_with_chunking(p_sum, raw_content, max_sum_chars, task_type="summary", log_callback=log_callback)
                    if ok: summary_result = res.strip()

                if gen_story:
                    if log_callback and callable(log_callback): 
                        log_callback("  └─ 📜 [旧・42回モード] 試行錯誤のストーリーを独立AI生成中...")
                    ok, res = self.send_request_with_chunking(p_story, raw_content, max_sum_chars, task_type="summary", log_callback=log_callback)
                    if ok: story_result = res.strip()

            # 🌟 主要タグの抽出 (共通)
            if gen_tags:
                if log_callback and callable(log_callback): 
                    log_callback("  └─ 🏷️ 主要タグをAI抽出中...")
                ok, res = self.execute_request_with_cooldown_retry(f"{p_tags}\n\n【対話ログ】\n{raw_content[:max_tag_chars]}", task_type="summary", log_callback=log_callback)
                if ok:
                    clean_t = res.replace("[", "").replace("]", "").replace("\"", "").replace("'", "")
                    extracted_tags = [t.strip() for t in clean_t.split(",") if t.strip()]

            start_t, end_t, service = "不明", "不明", "Google AI Studio"
            m_s = re.search(r'true_start_time:\s*"([^"]+)"', raw_content)
            m_e = re.search(r'true_end_time:\s*"([^"]+)"', raw_content)
            m_svc = re.search(r'ai_service:\s*"([^"]+)"', raw_content)
            if m_s: start_t = m_s.group(1)
            if m_e: end_t = m_e.group(1)
            if m_svc: service = m_svc.group(1)

            chat_name = os.path.basename(chat_folder_path)
            sum_filepath = os.path.join(chat_folder_path, f"summary_{chat_name}.md")
            tags_json = json.dumps(extracted_tags, ensure_ascii=False)
            
            md_out = [
                "---",
                f'ai_service: "{service}"',
                f'processed_turns: {raw_turns}',
                f'tags: {tags_json}',
                f'true_start_time: "{start_t}"',
                f'true_end_time: "{end_t}"',
                "---",
                f"\n# 📝 要約 ＆ 試行錯誤ストーリー: {chat_name}\n"
            ]

            if summary_mode == "mode_21" and summary_result:
                md_out.append(summary_result)
            else:
                if summary_result:
                    md_out.append(f"## 📌 概要 (Short Summary)\n{summary_result}\n")
                if story_result:
                    md_out.append(f"## 📜 試行錯誤のストーリー・経過プロセス\n{story_result}\n")

            with open(sum_filepath, "w", encoding="utf-8") as out_f:
                out_f.write("\n".join(md_out))

            return True, f"要約・ストーリー更新完了 ({raw_turns} ターン)"

        except Exception as e:
            return False, f"処理エラー: {e}"


class UsageHelpDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("❓ AiReAccessway 使い方ガイド")
        self.geometry("650x500")
        
        if os.path.exists(ICON_PORTAL):
            try: self.iconbitmap(ICON_PORTAL)
            except: pass

        self.build_widgets()

    def build_widgets(self):
        ttk.Label(self, text="📖 AiReAccessway システム使い方ガイド", font=("MS Gothic", 10, "bold")).pack(anchor="w", padx=10, pady=8)

        txt_frame = ttk.Frame(self, padding=10)
        txt_frame.pack(fill="both", expand=True)

        txt = tk.Text(txt_frame, wrap="word", font=("MS Gothic", 9), background="#ffffff")
        sb = ttk.Scrollbar(txt_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        guide_text = """======================================================================
 ⚓ AiReAccessway - 概要 ＆ 設定マニュアル
======================================================================

【1. 要約アルゴリズムモードの選択】
 ・新・推奨方式 (試行錯誤優先スキャン ➔ 概要二次生成):
   ストーリーを最優先で100%濃密抽出後、そのストーリーから概要を一発作成。
   高品質とスピード2倍・送信半減を両立します。

 ・一括同時生成 (概要・ストーリーの同一リクエスト並列要求):
   最も高速ですが要約が簡略化される場合があります。

 ・個別2往復 (概要・ストーリーの完全独立2回スキャン):
   旧・従来方式。概要とストーリーで2回独立スキャンします。
======================================================================
"""
        txt.insert(tk.END, guide_text)
        txt.config(state="disabled")


class PromptExamplesDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("📚 プロンプト用例テンプレート集")
        self.geometry("680x520")
        
        if os.path.exists(ICON_PORTAL):
            try: self.iconbitmap(ICON_PORTAL)
            except: pass

        self.build_widgets()

    def build_widgets(self):
        ttk.Label(self, text="📚 プロンプト用例テンプレート集 (コピーしてご活用ください)", font=("MS Gothic", 10, "bold")).pack(anchor="w", padx=10, pady=8)

        txt_frame = ttk.Frame(self, padding=10)
        txt_frame.pack(fill="both", expand=True)

        txt = tk.Text(txt_frame, wrap="word", font=("MS Gothic", 9), background="#ffffff")
        sb = ttk.Scrollbar(txt_frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        examples_text = """----------------------------------------------------------------------
【パターン 1: 泥臭い試行錯誤ストーリー重視】(デフォルト推奨)
----------------------------------------------------------------------
【指示】以下の対話ログから、ユーザーが何を目指し、どのようなエラー・勘違い・
失敗の足踏み（ループ）に遭遇し、最終的にどう解決したか（または未解決か）の
試行錯誤の経緯・プロセスを時系列で客観的に抽出してください。
"""
        txt.insert(tk.END, examples_text)
        txt.config(state="disabled")


class AiReAccesswayFrame(ttk.Frame):
    """メイン統合フレーム (3大要約モード選択ラジオボタン搭載版)"""
    def __init__(self, parent, config, save_callback=None):
        super().__init__(parent)
        self.config = config
        self.save_callback = save_callback
        
        self.controller = AiReAccesswayController(config)
        self.personas_list = self.config.get("personas", DEFAULT_PERSONAS)
        self.current_persona_idx = 0

        self.build_ui()
        self.load_config_to_ui()

    def build_ui(self):
        try:
            style = ttk.Style()            
            style.configure("SubNotebook.TNotebook", background="#f1f5f9", borderwidth=0)
            style.configure("SubNotebook.TNotebook.Tab", font=("MS Gothic", 9, "bold"), padding=[10, 4], background="#e2e8f0", foreground="#334155")
            style.map("SubNotebook.TNotebook.Tab",
                background=[("selected", "#ffffff"), ("active", "#f8fafc")],
                foreground=[("selected", "#0284c7"), ("active", "#0f172a")]
            )
        except: pass

        self.notebook = ttk.Notebook(self, style="SubNotebook.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        self.tab_hub = ttk.Frame(self.notebook, padding=10)
        self.tab_prompt = ttk.Frame(self.notebook, padding=10)
        self.tab_persona = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_hub, text=" 🧠 AI実行ハブ ＆ パラメーター設定 ")
        self.notebook.add(self.tab_prompt, text=" 📝 プロンプト編集 ")

        if HAS_API_MODULE:
            self.api_frame = AiReAPIFrame(self.notebook, self.controller.api_controller, self.config, self.save_callback)
            self.notebook.add(self.api_frame, text=" 🤖 AI API 接続設定 (AiReAPI) ")
        else:
            err_f = ttk.Frame(self.notebook, padding=20)
            ttk.Label(err_f, text="⚠️ AiReAPI.pyw が見つからないかエラーのため読み込めません。").pack()
            self.notebook.add(err_f, text=" 🤖 AI API 接続設定 (エラー) ")

        self.notebook.add(self.tab_persona, text=" 👤 ペルソナ（AI対話キャラ）設定 ")

        # --- タブ 1: AI実行ハブ ＆ パラメーター設定 ---
        hdr_f = ttk.Frame(self.tab_hub)
        hdr_f.pack(fill="x", pady=2)
        ttk.Label(hdr_f, text="🧠 AI処理オーケストレーター設定", font=("MS Gothic", 10, "bold")).pack(side="left")
        ttk.Button(hdr_f, text="❓ 使い方ヘルプ", command=lambda: UsageHelpDialog(self)).pack(side="right", padx=2)

        # 🌟 3大要約モード選択ラジオボタンの配置
        mode_lf = ttk.LabelFrame(self.tab_hub, text=" ⚡ 要約・ストーリー生成アルゴリズムモードの選択 ", padding=8)
        mode_lf.pack(fill="x", pady=4)

        self.summary_mode_var = tk.StringVar(value=self.config.get("summary_generation_mode", "mode_22"))

        rb_m22 = ttk.Radiobutton(
            mode_lf,
            text="📻 🚀 【新・推奨】 ストーリー主導 2段階モード (階層型2段階生成)",
            value="mode_22",
            variable=self.summary_mode_var
        )
        rb_m22.pack(anchor="w", pady=2)

        rb_m21 = ttk.Radiobutton(
            mode_lf,
            text="📻 ⚡ 【スピード最優先】 一括同時生成モード (シングルパス同時抽出)",
            value="mode_21",
            variable=self.summary_mode_var
        )
        rb_m21.pack(anchor="w", pady=2)

        rb_m42 = ttk.Radiobutton(
            mode_lf,
            text="📻 🐢 【従来・完全独立】 個別2往復モード (ダブルパス独立生成)",
            value="mode_42",
            variable=self.summary_mode_var
        )
        rb_m42.pack(anchor="w", pady=2)

        item_lf = ttk.LabelFrame(self.tab_hub, text=" [1] AIに自動生成させるコンテンツの選択 ", padding=8)
        item_lf.pack(fill="x", pady=4)

        self.var_gen_sum = tk.BooleanVar(value=True)
        self.var_gen_story = tk.BooleanVar(value=True)
        self.var_gen_tags = tk.BooleanVar(value=True)

        ttk.Checkbutton(item_lf, text="📌 概要 (Short Summary) を出力する", variable=self.var_gen_sum).pack(anchor="w", pady=2)
        ttk.Checkbutton(item_lf, text="📜 時系列ストーリー (試行錯誤・足踏み・解決の軌跡) を出力する", variable=self.var_gen_story).pack(anchor="w", pady=2)
        ttk.Checkbutton(item_lf, text="🏷 主要タグを自動抽出してヘッダー (YAML) に埋め込む", variable=self.var_gen_tags).pack(anchor="w", pady=2)

        trig_lf = ttk.LabelFrame(self.tab_hub, text=" [2] AI要約の自動更新タイミング（多角連動トリガー） ", padding=8)
        trig_lf.pack(fill="x", pady=4)

        v_box = ttk.Frame(trig_lf)
        v_box.pack(fill="x", padx=5)

        self.var_trig_manual = tk.BooleanVar(value=False)
        self.chk_manual = ttk.Checkbutton(
            v_box, 
            text="完全手動モード（「一括要約実行」ボタンを押した時のみ実行）", 
            variable=self.var_trig_manual,
            command=self.toggle_manual_mode_state
        )
        self.chk_manual.pack(anchor="w", pady=3)

        ttk.Separator(v_box, orient="horizontal").pack(fill="x", pady=4)

        grid_f = ttk.Frame(v_box)
        grid_f.pack(fill="x", pady=2)
        grid_f.columnconfigure(1, weight=1)

        t_txt_f = ttk.Frame(grid_f)
        t_txt_f.grid(row=0, column=0, sticky="w", pady=3)
        self.var_trig_turns = tk.BooleanVar(value=True)
        self.chk_turns = ttk.Checkbutton(t_txt_f, text="会話の差分ターン数指定:", variable=self.var_trig_turns)
        self.chk_turns.pack(side="left")
        self.spin_turns_var = tk.StringVar(value="10")
        self.spin_turns = ttk.Spinbox(t_txt_f, from_=3, to=50, width=4, textvariable=self.spin_turns_var)
        self.spin_turns.pack(side="left", padx=4)
        self.lbl_t_unit = ttk.Label(t_txt_f, text="ターン増えたら更新")
        self.lbl_t_unit.pack(side="left")

        self.slider_turns_var = tk.DoubleVar(value=10.0)
        self.slider_turns = ttk.Scale(grid_f, from_=3, to=50, variable=self.slider_turns_var, orient="horizontal", command=self.on_slider_turns_move)
        self.slider_turns.grid(row=0, column=1, sticky="ew", padx=(15, 5), pady=3)
        self.spin_turns.bind("<KeyRelease>", self.on_spin_turns_typed)

        d_txt_f = ttk.Frame(grid_f)
        d_txt_f.grid(row=1, column=0, sticky="w", pady=3)
        self.var_trig_days = tk.BooleanVar(value=False)
        self.chk_days = ttk.Checkbutton(d_txt_f, text="前回の要約から", variable=self.var_trig_days)
        self.chk_days.pack(side="left")
        self.spin_days_var = tk.StringVar(value="7")
        self.spin_days = ttk.Spinbox(d_txt_f, from_=1, to=30, width=4, textvariable=self.spin_days_var)
        self.spin_days.pack(side="left", padx=4)
        self.lbl_d_unit = ttk.Label(d_txt_f, text="日以上経過して発言追加があれば更新")
        self.lbl_d_unit.pack(side="left")

        self.slider_days_var = tk.DoubleVar(value=7.0)
        self.slider_days = ttk.Scale(grid_f, from_=1, to=30, variable=self.slider_days_var, orient="horizontal", command=self.on_slider_days_move)
        self.slider_days.grid(row=1, column=1, sticky="ew", padx=(15, 5), pady=3)
        self.spin_days.bind("<KeyRelease>", self.on_spin_days_typed)

        i_txt_f = ttk.Frame(grid_f)
        i_txt_f.grid(row=2, column=0, sticky="w", pady=3)
        self.var_trig_idle = tk.BooleanVar(value=True)
        self.chk_idle = ttk.Checkbutton(i_txt_f, text="放置・離脱検知: 無操作", variable=self.var_trig_idle)
        self.chk_idle.pack(side="left")
        self.spin_idle_var = tk.StringVar(value="5")
        self.spin_idle = ttk.Spinbox(i_txt_f, from_=1, to=60, width=4, textvariable=self.spin_idle_var)
        self.spin_idle.pack(side="left", padx=4)
        self.lbl_i_unit = ttk.Label(i_txt_f, text="分後に自動更新")
        self.lbl_i_unit.pack(side="left")

        self.slider_idle_var = tk.DoubleVar(value=5.0)
        self.slider_idle = ttk.Scale(grid_f, from_=2, to=60, variable=self.slider_idle_var, orient="horizontal", command=self.on_slider_idle_move)
        self.slider_idle.grid(row=2, column=1, sticky="ew", padx=(15, 5), pady=3)
        self.spin_idle.bind("<KeyRelease>", self.on_spin_idle_typed)

        ttk.Separator(v_box, orient="horizontal").pack(fill="x", pady=4)

        row_s = ttk.Frame(v_box)
        row_s.pack(fill="x", pady=2)
        self.var_trig_startup = tk.BooleanVar(value=True)
        self.chk_startup = ttk.Checkbutton(row_s, text="アプリ起動時に未要約ログの更新提案を行う", variable=self.var_trig_startup)
        self.chk_startup.pack(anchor="w")

        row_o = ttk.Frame(v_box)
        row_o.pack(fill="x", pady=2)
        self.var_trig_open = tk.BooleanVar(value=True)
        self.chk_open = ttk.Checkbutton(row_o, text="ポータルでチャットを開いた時に更新確認する", variable=self.var_trig_open)
        self.chk_open.pack(anchor="w")

        param_lf = ttk.LabelFrame(self.tab_hub, text=" [3] AI読込文字数 ＆ 分割・リトライ制御 ", padding=8)
        param_lf.pack(fill="x", pady=4)

        p_grid = ttk.Frame(param_lf)
        p_grid.pack(fill="x", pady=2)
        p_grid.columnconfigure(1, weight=1)

        row_p1_lbl = ttk.Frame(p_grid)
        row_p1_lbl.grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(row_p1_lbl, text="要約用1回送信上限:").pack(side="left")
        self.spin_max_sum_var = tk.StringVar(value="50000")
        self.spin_max_sum = ttk.Spinbox(row_p1_lbl, from_=10000, to=200000, increment=5000, width=7, textvariable=self.spin_max_sum_var)
        self.spin_max_sum.pack(side="left", padx=4)
        ttk.Label(row_p1_lbl, text="文字").pack(side="left")

        self.slider_max_sum_var = tk.DoubleVar(value=50000.0)
        self.slider_max_sum = ttk.Scale(p_grid, from_=10000, to=200000, variable=self.slider_max_sum_var, orient="horizontal", command=self.on_slider_max_sum_move)
        self.slider_max_sum.grid(row=0, column=1, sticky="ew", padx=(15, 5), pady=3)
        self.spin_max_sum.bind("<KeyRelease>", self.on_spin_max_sum_typed)

        row_p2 = ttk.Frame(p_grid)
        row_p2.grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
        self.var_enable_chunking = tk.BooleanVar(value=True)
        ttk.Checkbutton(row_p2, text="✂️ 上限を超える長大ログを数パートに自動分割して段階AI要約し、100%網羅統合する", variable=self.var_enable_chunking).pack(side="left")

        row_p2_2 = ttk.Frame(p_grid)
        row_p2_2.grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
        self.var_enable_smart_delay = tk.BooleanVar(value=True)
        self.var_enable_cooldown_retry = tk.BooleanVar(value=True)
        ttk.Checkbutton(row_p2_2, text="⏱️ 送信文字数に応じた動的スマートディレイ（可変待機）", variable=self.var_enable_smart_delay).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(row_p2_2, text="🛡️ 429 レート制限検知時に自動冷却待機してリトライする", variable=self.var_enable_cooldown_retry).pack(side="left")

        row_cool = ttk.Frame(p_grid)
        row_cool.grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(row_cool, text="429制限検知時の冷却待機時間:").pack(side="left")
        self.spin_cooldown_var = tk.StringVar(value="60")
        self.spin_cooldown = ttk.Spinbox(row_cool, from_=10, to=300, increment=5, width=5, textvariable=self.spin_cooldown_var)
        self.spin_cooldown.pack(side="left", padx=4)
        ttk.Label(row_cool, text="秒 (標準: 60秒)").pack(side="left")

        row_p3_lbl = ttk.Frame(p_grid)
        row_p3_lbl.grid(row=4, column=0, sticky="w", pady=3)
        ttk.Label(row_p3_lbl, text="タグ抽出用上限:").pack(side="left")
        self.spin_max_tag_var = tk.StringVar(value="10000")
        self.spin_max_tag = ttk.Spinbox(row_p3_lbl, from_=3000, to=50000, increment=1000, width=7, textvariable=self.spin_max_tag_var)
        self.spin_max_tag.pack(side="left", padx=4)
        ttk.Label(row_p3_lbl, text="文字").pack(side="left")

        self.slider_max_tag_var = tk.DoubleVar(value=10000.0)
        self.slider_max_tag = ttk.Scale(p_grid, from_=3000, to=50000, variable=self.slider_max_tag_var, orient="horizontal", command=self.on_slider_max_tag_move)
        self.slider_max_tag.grid(row=4, column=1, sticky="ew", padx=(15, 5), pady=3)
        self.spin_max_tag.bind("<KeyRelease>", self.on_spin_max_tag_typed)

        scale_lf = ttk.LabelFrame(self.tab_hub, text=" [3.5] 4段階可変スケールディレイ設定（規模別文字数 ＆ 待機秒数） ", padding=8)
        scale_lf.pack(fill="x", pady=4)

        sc_grid = ttk.Frame(scale_lf)
        sc_grid.pack(fill="x", pady=2)

        row_s_lbl = ttk.Frame(sc_grid)
        row_s_lbl.grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(row_s_lbl, text="1. 小規模: ").pack(side="left")
        self.spin_sc_small_chars_var = tk.StringVar(value="50000")
        ttk.Spinbox(row_s_lbl, from_=10000, to=100000, increment=5000, width=7, textvariable=self.spin_sc_small_chars_var).pack(side="left", padx=2)
        ttk.Label(row_s_lbl, text="文字まで ➔ 待機:").pack(side="left", padx=2)
        self.spin_sc_small_delay_var = tk.StringVar(value="4.5")
        ttk.Spinbox(row_s_lbl, from_=1.0, to=50.0, increment=0.5, width=5, textvariable=self.spin_sc_small_delay_var).pack(side="left", padx=2)
        ttk.Label(row_s_lbl, text="秒").pack(side="left")

        row_m_lbl = ttk.Frame(sc_grid)
        row_m_lbl.grid(row=1, column=0, sticky="w", pady=3)
        ttk.Label(row_m_lbl, text="2. 中規模: ").pack(side="left")
        self.spin_sc_med_chars_var = tk.StringVar(value="200000")
        ttk.Spinbox(row_m_lbl, from_=50000, to=400000, increment=10000, width=7, textvariable=self.spin_sc_med_chars_var).pack(side="left", padx=2)
        ttk.Label(row_m_lbl, text="文字まで ➔ 待機:").pack(side="left", padx=2)
        self.spin_sc_med_delay_var = tk.StringVar(value="15.0")
        ttk.Spinbox(row_m_lbl, from_=1.0, to=60.0, increment=1.0, width=5, textvariable=self.spin_sc_med_delay_var).pack(side="left", padx=2)
        ttk.Label(row_m_lbl, text="秒").pack(side="left")

        row_l_lbl = ttk.Frame(sc_grid)
        row_l_lbl.grid(row=2, column=0, sticky="w", pady=3)
        ttk.Label(row_l_lbl, text="3. 大規模: ").pack(side="left")
        self.spin_sc_large_chars_var = tk.StringVar(value="500000")
        ttk.Spinbox(row_l_lbl, from_=200000, to=800000, increment=50000, width=7, textvariable=self.spin_sc_large_chars_var).pack(side="left", padx=2)
        ttk.Label(row_l_lbl, text="文字まで ➔ 待機:").pack(side="left", padx=2)
        self.spin_sc_large_delay_var = tk.StringVar(value="30.0")
        ttk.Spinbox(row_l_lbl, from_=1.0, to=120.0, increment=1.0, width=5, textvariable=self.spin_sc_large_delay_var).pack(side="left", padx=2)
        ttk.Label(row_l_lbl, text="秒").pack(side="left")

        row_h_lbl = ttk.Frame(sc_grid)
        row_h_lbl.grid(row=3, column=0, sticky="w", pady=3)
        ttk.Label(row_h_lbl, text="4. 超極大: ").pack(side="left")
        self.spin_sc_huge_chars_var = tk.StringVar(value="1000000")
        ttk.Spinbox(row_h_lbl, from_=500000, to=5000000, increment=100000, width=8, textvariable=self.spin_sc_huge_chars_var).pack(side="left", padx=2)
        ttk.Label(row_h_lbl, text="文字以上 ➔ 待機:").pack(side="left", padx=2)
        self.spin_sc_huge_delay_var = tk.StringVar(value="60.0")
        ttk.Spinbox(row_h_lbl, from_=1.0, to=300.0, increment=5.0, width=5, textvariable=self.spin_sc_huge_delay_var).pack(side="left", padx=2)
        ttk.Label(row_h_lbl, text="秒").pack(side="left")

        delay_lf = ttk.LabelFrame(self.tab_hub, text=" [4] レート制限・APIディレイ基本設定 (1秒〜50秒) ", padding=8)
        delay_lf.pack(fill="x", pady=4)

        row_del = ttk.Frame(delay_lf)
        row_del.pack(fill="x")
        ttk.Label(row_del, text="標準送信間隔:").pack(side="left")
        self.spin_delay_var = tk.StringVar(value="4.5")
        self.spin_delay = ttk.Spinbox(row_del, from_=1.0, to=50.0, increment=0.5, width=5, textvariable=self.spin_delay_var)
        self.spin_delay.pack(side="left", padx=4)
        ttk.Label(row_del, text="秒 (標準推奨: 4.5秒)").pack(side="left", padx=2)

        self.slider_delay_var = tk.DoubleVar(value=4.5)
        self.slider_delay = ttk.Scale(row_del, from_=1.0, to=50.0, variable=self.slider_delay_var, orient="horizontal", command=self.on_slider_delay_move)
        self.slider_delay.pack(side="left", fill="x", expand=True, padx=8)
        self.spin_delay.bind("<KeyRelease>", self.on_spin_delay_typed)

        ttk.Button(self.tab_hub, text="💾 Accessway AIハブ設定を保存", command=self.save_config_from_ui).pack(fill="x", pady=6)

        # =========================================================================
        # --- タブ 2: プロンプトカスタム編集 ---
        # =========================================================================
        p_hdr = ttk.Frame(self.tab_prompt)
        p_hdr.pack(fill="x", pady=2)
        ttk.Label(p_hdr, text="📝 プロンプトカスタム編集", font=("MS Gothic", 10, "bold")).pack(side="left")
        
        ttk.Button(p_hdr, text="💾 プロンプト設定を保存", command=self.save_config_from_ui).pack(side="right", padx=2)
        ttk.Button(p_hdr, text="🔄 推奨復元", command=self.reset_default_prompts).pack(side="right", padx=2)
        ttk.Button(p_hdr, text="🧹 一括クリア", command=self.clear_all_prompts).pack(side="right", padx=2)
        ttk.Button(p_hdr, text="📚 用例集", command=lambda: PromptExamplesDialog(self)).pack(side="right", padx=2)
        ttk.Button(p_hdr, text="❓ ヘルプ", command=lambda: UsageHelpDialog(self)).pack(side="right", padx=2)

        self.prompt_pane = tk.PanedWindow(self.tab_prompt, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
        self.prompt_pane.pack(fill="both", expand=True, pady=4)

        f_p1 = ttk.Frame(self.prompt_pane)
        ttk.Label(f_p1, text="📌 【基本要約】概要生成プロンプト:", font=("MS Gothic", 9, "bold")).pack(anchor="w", pady=1)
        f_txt1 = ttk.Frame(f_p1); f_txt1.pack(fill="both", expand=True)
        self.txt_p_sum = tk.Text(f_txt1, font=("MS Gothic", 9), wrap="word")
        sb1 = ttk.Scrollbar(f_txt1, command=self.txt_p_sum.yview)
        self.txt_p_sum.configure(yscrollcommand=sb1.set)
        self.txt_p_sum.pack(side="left", fill="both", expand=True); sb1.pack(side="right", fill="y")

        f_p2 = ttk.Frame(self.prompt_pane)
        ttk.Label(f_p2, text="📜 【基本要約】ストーリー抽出プロンプト:", font=("MS Gothic", 9, "bold")).pack(anchor="w", pady=1)
        f_txt2 = ttk.Frame(f_p2); f_txt2.pack(fill="both", expand=True)
        self.txt_p_story = tk.Text(f_txt2, font=("MS Gothic", 9), wrap="word")
        sb2 = ttk.Scrollbar(f_txt2, command=self.txt_p_story.yview)
        self.txt_p_story.configure(yscrollcommand=sb2.set)
        self.txt_p_story.pack(side="left", fill="both", expand=True); sb2.pack(side="right", fill="y")

        f_p3 = ttk.Frame(self.prompt_pane)
        ttk.Label(f_p3, text="🏷 【基本要約】主要タグ抽出プロンプト:", font=("MS Gothic", 9, "bold")).pack(anchor="w", pady=1)
        f_txt3 = ttk.Frame(f_p3); f_txt3.pack(fill="both", expand=True)
        self.txt_p_tags = tk.Text(f_txt3, font=("MS Gothic", 9), wrap="word")
        sb3 = ttk.Scrollbar(f_txt3, command=self.txt_p_tags.yview)
        self.txt_p_tags.configure(yscrollcommand=sb3.set)
        self.txt_p_tags.pack(side="left", fill="both", expand=True); sb3.pack(side="right", fill="y")

        f_p_f1 = ttk.Frame(self.prompt_pane)
        ttk.Label(f_p_f1, text="🔨 【Forge】全文マージ＆概要プロンプト:", font=("MS Gothic", 9, "bold"), foreground="#0284c7").pack(anchor="w", pady=1)
        f_txt_f1 = ttk.Frame(f_p_f1); f_txt_f1.pack(fill="both", expand=True)
        self.txt_p_forge_full = tk.Text(f_txt_f1, font=("MS Gothic", 9), wrap="word")
        sb_f1 = ttk.Scrollbar(f_txt_f1, command=self.txt_p_forge_full.yview)
        self.txt_p_forge_full.configure(yscrollcommand=sb_f1.set)
        self.txt_p_forge_full.pack(side="left", fill="both", expand=True); sb_f1.pack(side="right", fill="y")

        f_p_f2 = ttk.Frame(self.prompt_pane)
        ttk.Label(f_p_f2, text="🔨 【Forge】特定トピック部分抽出プロンプト:", font=("MS Gothic", 9, "bold"), foreground="#0284c7").pack(anchor="w", pady=1)
        f_txt_f2 = ttk.Frame(f_p_f2); f_txt_f2.pack(fill="both", expand=True)
        self.txt_p_forge_topic = tk.Text(f_txt_f2, font=("MS Gothic", 9), wrap="word")
        sb_f2 = ttk.Scrollbar(f_txt_f2, command=self.txt_p_forge_topic.yview)
        self.txt_p_forge_topic.configure(yscrollcommand=sb_f2.set)
        self.txt_p_forge_topic.pack(side="left", fill="both", expand=True); sb_f2.pack(side="right", fill="y")

        f_p_f3 = ttk.Frame(self.prompt_pane)
        ttk.Label(f_p_f3, text="🔨 【Forge】試行錯誤・エラー解決経緯プロンプト:", font=("MS Gothic", 9, "bold"), foreground="#0284c7").pack(anchor="w", pady=1)
        f_txt_f3 = ttk.Frame(f_p_f3); f_txt_f3.pack(fill="both", expand=True)
        self.txt_p_forge_story = tk.Text(f_txt_f3, font=("MS Gothic", 9), wrap="word")
        sb_f3 = ttk.Scrollbar(f_txt_f3, command=self.txt_p_forge_story.yview)
        self.txt_p_forge_story.configure(yscrollcommand=sb_f3.set)
        self.txt_p_forge_story.pack(side="left", fill="both", expand=True); sb_f3.pack(side="right", fill="y")

        f_p_c1 = ttk.Frame(self.prompt_pane)
        c1_hdr = ttk.Frame(f_p_c1); c1_hdr.pack(fill="x", pady=1)
        ttk.Label(c1_hdr, text="💡 【Forgeカスタムボタン1】 ボタン名:", font=("MS Gothic", 9, "bold"), foreground="#16a34a").pack(side="left")
        self.entry_p_forge_c1_label = ttk.Entry(c1_hdr, width=22)
        self.entry_p_forge_c1_label.pack(side="left", padx=5)

        f_txt_c1 = ttk.Frame(f_p_c1); f_txt_c1.pack(fill="both", expand=True)
        self.txt_p_forge_c1_prompt = tk.Text(f_txt_c1, font=("MS Gothic", 9), wrap="word")
        sb_c1 = ttk.Scrollbar(f_txt_c1, command=self.txt_p_forge_c1_prompt.yview)
        self.txt_p_forge_c1_prompt.configure(yscrollcommand=sb_c1.set)
        self.txt_p_forge_c1_prompt.pack(side="left", fill="both", expand=True); sb_c1.pack(side="right", fill="y")

        f_p_c2 = ttk.Frame(self.prompt_pane)
        c2_hdr = ttk.Frame(f_p_c2); c2_hdr.pack(fill="x", pady=1)
        ttk.Label(c2_hdr, text="💡 【Forgeカスタムボタン2】 ボタン名:", font=("MS Gothic", 9, "bold"), foreground="#16a34a").pack(side="left")
        self.entry_p_forge_c2_label = ttk.Entry(c2_hdr, width=22)
        self.entry_p_forge_c2_label.pack(side="left", padx=5)

        f_txt_c2 = ttk.Frame(f_p_c2); f_txt_c2.pack(fill="both", expand=True)
        self.txt_p_forge_c2_prompt = tk.Text(f_txt_c2, font=("MS Gothic", 9), wrap="word")
        sb_c2 = ttk.Scrollbar(f_txt_c2, command=self.txt_p_forge_c2_prompt.yview)
        self.txt_p_forge_c2_prompt.configure(yscrollcommand=sb_c2.set)
        self.txt_p_forge_c2_prompt.pack(side="left", fill="both", expand=True); sb_c2.pack(side="right", fill="y")

        f_p_end = ttk.Frame(self.prompt_pane)

        self.prompt_pane.add(f_p1, minsize=40, height=70)
        self.prompt_pane.add(f_p2, minsize=40, height=70)
        self.prompt_pane.add(f_p3, minsize=40, height=50)
        self.prompt_pane.add(f_p_f1, minsize=40, height=70)
        self.prompt_pane.add(f_p_f2, minsize=40, height=70)
        self.prompt_pane.add(f_p_f3, minsize=40, height=70)
        self.prompt_pane.add(f_p_c1, minsize=50, height=80)
        self.prompt_pane.add(f_p_c2, minsize=50, height=80)
        self.prompt_pane.add(f_p_end, minsize=10, height=20)

        # =========================================================================
        # --- タブ 4: 👤 ペルソナ（AI対話キャラ）設定 ---
        # =========================================================================
        pers_hdr = ttk.Frame(self.tab_persona)
        pers_hdr.pack(fill="x", pady=2)

        ttk.Label(pers_hdr, text="👤 AI対話ペルソナ（キャラクター）管理 ＆ プロンプト編集", font=("MS Gothic", 10, "bold")).pack(side="left")
        ttk.Button(pers_hdr, text="💾 全ペルソナ設定を保存", command=self.save_config_from_ui).pack(side="right", padx=2)
        ttk.Button(pers_hdr, text="🔄 初期デフォルトに復元", command=self.reset_default_personas).pack(side="right", padx=2)

        pers_f = ttk.LabelFrame(self.tab_persona, text=" 📌 ペルソナの選択 ＆ 個別プロンプト編集 ", padding=10)
        pers_f.pack(fill="both", expand=True, pady=4)

        select_row = ttk.Frame(pers_f)
        select_row.pack(fill="x", pady=4)

        ttk.Label(select_row, text="編集するペルソナ:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=2)
        self.combo_persona_var = tk.StringVar()
        self.combo_persona = ttk.Combobox(select_row, textvariable=self.combo_persona_var, state="readonly", width=26)
        self.combo_persona.pack(side="left", padx=5)
        self.combo_persona.bind("<<ComboboxSelected>>", self.on_persona_selected)

        ttk.Button(select_row, text="➕ 新規作成", command=self.add_new_persona).pack(side="left", padx=4)
        ttk.Button(select_row, text="🗑️ 削除", command=self.delete_current_persona).pack(side="left", padx=2)

        ttk.Separator(pers_f, orient="horizontal").pack(fill="x", pady=8)

        edit_meta_f = ttk.Frame(pers_f)
        edit_meta_f.pack(fill="x", pady=2)

        ttk.Label(edit_meta_f, text="📌 ペルソナ表示名:", font=("MS Gothic", 9, "bold")).pack(side="left", padx=2)
        self.entry_persona_name = ttk.Entry(edit_meta_f, font=("MS Gothic", 9), width=30)
        self.entry_persona_name.pack(side="left", padx=5)
        self.entry_persona_name.bind("<KeyRelease>", self.on_persona_name_edited)

        ttk.Label(pers_f, text="📝 システムプロンプト（AIに与える役割・性格・口調・振る舞い・指示文）:", font=("MS Gothic", 9, "bold")).pack(anchor="w", pady=(8, 2))

        txt_p_f = ttk.Frame(pers_f)
        txt_p_f.pack(fill="both", expand=True, pady=2)

        self.txt_persona_prompt = tk.Text(txt_p_f, font=("MS Gothic", 9), wrap="word", background="#ffffff")
        sb_pers = ttk.Scrollbar(txt_p_f, command=self.txt_persona_prompt.yview)
        self.txt_persona_prompt.configure(yscrollcommand=sb_pers.set)
        
        self.txt_persona_prompt.pack(side="left", fill="both", expand=True)
        sb_pers.pack(side="right", fill="y")
        self.txt_persona_prompt.bind("<KeyRelease>", self.on_persona_prompt_edited)

    # --- ペルソナ管理メソッド群 ---
    def update_persona_combo_list(self):
        names = [p.get("name", "名称未設定") for p in self.personas_list]
        self.combo_persona["values"] = names
        if names:
            if self.current_persona_idx >= len(names):
                self.current_persona_idx = 0
            self.combo_persona.current(self.current_persona_idx)
            self.load_persona_fields(self.current_persona_idx)

    def on_persona_selected(self, event=None):
        idx = self.combo_persona.current()
        if idx >= 0:
            self.current_persona_idx = idx
            self.load_persona_fields(idx)

    def load_persona_fields(self, idx):
        if 0 <= idx < len(self.personas_list):
            p = self.personas_list[idx]
            self.entry_persona_name.delete(0, tk.END)
            self.entry_persona_name.insert(0, p.get("name", ""))
            
            self.txt_persona_prompt.delete("1.0", tk.END)
            self.txt_persona_prompt.insert("1.0", p.get("system_prompt", ""))

    def on_persona_name_edited(self, event=None):
        if 0 <= self.current_persona_idx < len(self.personas_list):
            new_name = self.entry_persona_name.get().strip()
            self.personas_list[self.current_persona_idx]["name"] = new_name
            
            names = [p.get("name", "名称未設定") for p in self.personas_list]
            self.combo_persona["values"] = names
            self.combo_persona.current(self.current_persona_idx)

    def on_persona_prompt_edited(self, event=None):
        if 0 <= self.current_persona_idx < len(self.personas_list):
            new_prompt = self.txt_persona_prompt.get("1.0", tk.END).strip()
            self.personas_list[self.current_persona_idx]["system_prompt"] = new_prompt

    def add_new_persona(self):
        new_p = {
            "id": f"persona_{int(time.time())}",
            "name": f"新規ペルソナ {len(self.personas_list) + 1}",
            "system_prompt": "あなたは優秀なAIアシスタントです。"
        }
        self.personas_list.append(new_p)
        self.current_persona_idx = len(self.personas_list) - 1
        self.update_persona_combo_list()

    def delete_current_persona(self):
        if len(self.personas_list) <= 1:
            messagebox.showwarning("警告", "最低1つのペルソナは残す必要があります。")
            return

        if messagebox.askyesno("削除確認", f"ペルソナ『{self.personas_list[self.current_persona_idx].get('name')}』を削除しますか？"):
            del self.personas_list[self.current_persona_idx]
            self.current_persona_idx = max(0, self.current_persona_idx - 1)
            self.update_persona_combo_list()

    def reset_default_personas(self):
        if messagebox.askyesno("復元確認", "ペルソナ設定を初期状態（デフォルト3種）に戻しますか？"):
            self.personas_list = json.loads(json.dumps(DEFAULT_PERSONAS))
            self.current_persona_idx = 0
            self.update_persona_combo_list()

    def toggle_manual_mode_state(self):
        is_manual = self.var_trig_manual.get()
        state_str = "disabled" if is_manual else "normal"

        self.chk_turns.config(state=state_str)
        self.spin_turns.config(state=state_str)
        self.slider_turns.config(state=state_str)
        self.lbl_t_unit.config(state=state_str)

        self.chk_days.config(state=state_str)
        self.spin_days.config(state=state_str)
        self.slider_days.config(state=state_str)
        self.lbl_d_unit.config(state=state_str)

        self.chk_idle.config(state=state_str)
        self.spin_idle.config(state=state_str)
        self.slider_idle.config(state=state_str)
        self.lbl_i_unit.config(state=state_str)

        self.chk_startup.config(state="normal")
        self.chk_open.config(state="normal")

    def on_slider_max_sum_move(self, val):
        self.spin_max_sum_var.set(str(int(float(val))))

    def on_spin_max_sum_typed(self, event=None):
        try:
            v = float(self.spin_max_sum_var.get())
            if 10000 <= v <= 200000: self.slider_max_sum_var.set(v)
        except: pass

    def on_slider_max_tag_move(self, val):
        self.spin_max_tag_var.set(str(int(float(val))))

    def on_spin_max_tag_typed(self, event=None):
        try:
            v = float(self.spin_max_tag_var.get())
            if 3000 <= v <= 50000: self.slider_max_tag_var.set(v)
        except: pass

    def on_slider_turns_move(self, val):
        self.spin_turns_var.set(str(int(float(val))))

    def on_spin_turns_typed(self, event=None):
        try:
            v = float(self.spin_turns_var.get())
            if 3 <= v <= 50: self.slider_turns_var.set(v)
        except: pass

    def on_slider_days_move(self, val):
        self.spin_days_var.set(str(int(float(val))))

    def on_spin_days_typed(self, event=None):
        try:
            v = float(self.spin_days_var.get())
            if 1 <= v <= 30: self.slider_days_var.set(v)
        except: pass

    def on_slider_idle_move(self, val):
        self.spin_idle_var.set(str(int(float(val))))

    def on_spin_idle_typed(self, event=None):
        try:
            v = float(self.spin_idle_var.get())
            if 1 <= v <= 60: self.slider_idle_var.set(v)
        except: pass

    def on_slider_delay_move(self, val):
        self.spin_delay_var.set(f"{float(val):.1f}")

    def on_spin_delay_typed(self, event=None):
        try:
            v = float(self.spin_delay_var.get())
            if 1.0 <= v <= 50.0: self.slider_delay_var.set(v)
        except: pass

    def clear_all_prompts(self):
        self.txt_p_sum.delete("1.0", tk.END)
        self.txt_p_story.delete("1.0", tk.END)
        self.txt_p_tags.delete("1.0", tk.END)
        self.txt_p_forge_full.delete("1.0", tk.END)
        self.txt_p_forge_topic.delete("1.0", tk.END)
        self.txt_p_forge_story.delete("1.0", tk.END)
        self.entry_p_forge_c1_label.delete(0, tk.END)
        self.txt_p_forge_c1_prompt.delete("1.0", tk.END)
        self.entry_p_forge_c2_label.delete(0, tk.END)
        self.txt_p_forge_c2_prompt.delete("1.0", tk.END)

    def reset_default_prompts(self):
        self.clear_all_prompts()
        self.txt_p_sum.insert(tk.END, DEFAULT_PROMPT_SUMMARY)
        self.txt_p_story.insert(tk.END, DEFAULT_PROMPT_STORY)
        self.txt_p_tags.insert(tk.END, DEFAULT_PROMPT_TAGS)
        self.txt_p_forge_full.insert(tk.END, DEFAULT_PROMPT_FORGE_FULL)
        self.txt_p_forge_topic.insert(tk.END, DEFAULT_PROMPT_FORGE_TOPIC)
        self.txt_p_forge_story.insert(tk.END, DEFAULT_PROMPT_FORGE_STORY)
        self.entry_p_forge_c1_label.insert(0, DEFAULT_PROMPT_FORGE_C1_LABEL)
        self.txt_p_forge_c1_prompt.insert(tk.END, DEFAULT_PROMPT_FORGE_C1_PROMPT)
        self.entry_p_forge_c2_label.insert(0, DEFAULT_PROMPT_FORGE_C2_LABEL)
        self.txt_p_forge_c2_prompt.insert(tk.END, DEFAULT_PROMPT_FORGE_C2_PROMPT)

    def load_config_to_ui(self):
        # 🌟 アルゴリズムモードのロード (未設定時は mode_22 デフォルト)
        self.summary_mode_var.set(self.config.get("summary_generation_mode", "mode_22"))

        self.var_gen_sum.set(self.config.get("gen_enable_summary", True))
        self.var_gen_story.set(self.config.get("gen_enable_story", True))
        self.var_gen_tags.set(self.config.get("gen_enable_tags", True))

        self.var_trig_manual.set(self.config.get("trig_manual_only", False))
        self.var_trig_turns.set(self.config.get("trig_turns_enabled", True))
        self.var_trig_days.set(self.config.get("trig_days_enabled", False))
        self.var_trig_idle.set(self.config.get("trig_idle_enabled", True))
        self.var_trig_startup.set(self.config.get("trig_startup_check", True))
        self.var_trig_open.set(self.config.get("trig_open_check", True))

        turns = self.config.get("diff_min_turns", 10)
        self.spin_turns_var.set(str(turns))
        self.slider_turns_var.set(float(turns))

        days = self.config.get("trig_min_days", 7)
        self.spin_days_var.set(str(days))
        self.slider_days_var.set(float(days))

        idle_mins = self.config.get("trig_idle_minutes", 5)
        self.spin_idle_var.set(str(idle_mins))
        self.slider_idle_var.set(float(idle_mins))

        delay = self.config.get("delay_seconds", 4.5)
        self.spin_delay_var.set(f"{delay:.1f}")
        self.slider_delay_var.set(float(delay))

        max_sum = self.config.get("max_summary_text_length", 50000)
        self.spin_max_sum_var.set(str(max_sum))
        self.slider_max_sum_var.set(float(max_sum))

        self.var_enable_chunking.set(self.config.get("enable_text_chunking", True))
        self.var_enable_smart_delay.set(self.config.get("enable_smart_delay", True))
        self.var_enable_cooldown_retry.set(self.config.get("enable_cooldown_retry", True))

        self.spin_cooldown_var.set(str(self.config.get("cooldown_seconds", 60)))

        self.spin_sc_small_chars_var.set(str(self.config.get("scale_small_chars", DEFAULT_SCALE_SMALL_CHARS)))
        self.spin_sc_small_delay_var.set(str(self.config.get("scale_small_delay", DEFAULT_SCALE_SMALL_DELAY)))

        self.spin_sc_med_chars_var.set(str(self.config.get("scale_medium_chars", DEFAULT_SCALE_MEDIUM_CHARS)))
        self.spin_sc_med_delay_var.set(str(self.config.get("scale_medium_delay", DEFAULT_SCALE_MEDIUM_DELAY)))

        self.spin_sc_large_chars_var.set(str(self.config.get("scale_large_chars", DEFAULT_SCALE_LARGE_CHARS)))
        self.spin_sc_large_delay_var.set(str(self.config.get("scale_large_delay", DEFAULT_SCALE_LARGE_DELAY)))

        self.spin_sc_huge_chars_var.set(str(self.config.get("scale_huge_chars", DEFAULT_SCALE_HUGE_CHARS)))
        self.spin_sc_huge_delay_var.set(str(self.config.get("scale_huge_delay", DEFAULT_SCALE_HUGE_DELAY)))

        max_tag = self.config.get("max_tags_text_length", 10000)
        self.spin_max_tag_var.set(str(max_tag))
        self.slider_max_tag_var.set(float(max_tag))

        self.clear_all_prompts()
        self.txt_p_sum.insert(tk.END, self.config.get("prompt_summary", DEFAULT_PROMPT_SUMMARY))
        self.txt_p_story.insert(tk.END, self.config.get("prompt_story", DEFAULT_PROMPT_STORY))
        self.txt_p_tags.insert(tk.END, self.config.get("prompt_tags", DEFAULT_PROMPT_TAGS))

        self.txt_p_forge_full.insert(tk.END, self.config.get("prompt_forge_full", DEFAULT_PROMPT_FORGE_FULL))
        self.txt_p_forge_topic.insert(tk.END, self.config.get("prompt_forge_topic", DEFAULT_PROMPT_FORGE_TOPIC))
        self.txt_p_forge_story.insert(tk.END, self.config.get("prompt_forge_story", DEFAULT_PROMPT_FORGE_STORY))

        self.entry_p_forge_c1_label.insert(0, self.config.get("prompt_forge_c1_label", DEFAULT_PROMPT_FORGE_C1_LABEL))
        self.txt_p_forge_c1_prompt.insert(tk.END, self.config.get("prompt_forge_c1_prompt", DEFAULT_PROMPT_FORGE_C1_PROMPT))

        self.entry_p_forge_c2_label.insert(0, self.config.get("prompt_forge_c2_label", DEFAULT_PROMPT_FORGE_C2_LABEL))
        self.txt_p_forge_c2_prompt.insert(tk.END, self.config.get("prompt_forge_c2_prompt", DEFAULT_PROMPT_FORGE_C2_PROMPT))

        # ペルソナデータのロード
        self.personas_list = self.config.get("personas", json.loads(json.dumps(DEFAULT_PERSONAS)))
        self.update_persona_combo_list()

        self.toggle_manual_mode_state()

    def save_config_from_ui(self):
        # 🌟 アルゴリズムモードの保存
        self.config["summary_generation_mode"] = self.summary_mode_var.get()

        self.config["gen_enable_summary"] = self.var_gen_sum.get()
        self.config["gen_enable_story"] = self.var_gen_story.get()
        self.config["gen_enable_tags"] = self.var_gen_tags.get()

        self.config["trig_manual_only"] = self.var_trig_manual.get()
        self.config["trig_turns_enabled"] = self.var_trig_turns.get()
        self.config["trig_days_enabled"] = self.var_trig_days.get()
        self.config["trig_idle_enabled"] = self.var_trig_idle.get()
        self.config["trig_startup_check"] = self.var_trig_startup.get()
        self.config["trig_open_check"] = self.var_trig_open.get()

        try: self.config["diff_min_turns"] = int(float(self.spin_turns_var.get()))
        except: self.config["diff_min_turns"] = 10

        try: self.config["trig_min_days"] = int(float(self.spin_days_var.get()))
        except: self.config["trig_min_days"] = 7

        try: self.config["trig_idle_minutes"] = int(float(self.spin_idle_var.get()))
        except: self.config["trig_idle_minutes"] = 5

        try: self.config["delay_seconds"] = round(float(self.spin_delay_var.get()), 1)
        except: self.config["delay_seconds"] = 4.5

        try: self.config["max_summary_text_length"] = int(float(self.spin_max_sum_var.get()))
        except: self.config["max_summary_text_length"] = 50000

        self.config["enable_text_chunking"] = self.var_enable_chunking.get()
        self.config["enable_smart_delay"] = self.var_enable_smart_delay.get()
        self.config["enable_cooldown_retry"] = self.var_enable_cooldown_retry.get()

        try: self.config["cooldown_seconds"] = int(float(self.spin_cooldown_var.get()))
        except: self.config["cooldown_seconds"] = 60

        try: self.config["scale_small_chars"] = int(float(self.spin_sc_small_chars_var.get()))
        except: self.config["scale_small_chars"] = DEFAULT_SCALE_SMALL_CHARS

        try: self.config["scale_small_delay"] = float(self.spin_sc_small_delay_var.get())
        except: self.config["scale_small_delay"] = DEFAULT_SCALE_SMALL_DELAY

        try: self.config["scale_medium_chars"] = int(float(self.spin_sc_med_chars_var.get()))
        except: self.config["scale_medium_chars"] = DEFAULT_SCALE_MEDIUM_CHARS

        try: self.config["scale_medium_delay"] = float(self.spin_sc_med_delay_var.get())
        except: self.config["scale_medium_delay"] = DEFAULT_SCALE_MEDIUM_DELAY

        try: self.config["scale_large_chars"] = int(float(self.spin_sc_large_chars_var.get()))
        except: self.config["scale_large_chars"] = DEFAULT_SCALE_LARGE_CHARS

        try: self.config["scale_large_delay"] = float(self.spin_sc_large_delay_var.get())
        except: self.config["scale_large_delay"] = DEFAULT_SCALE_LARGE_DELAY

        try: self.config["scale_huge_chars"] = int(float(self.spin_sc_huge_chars_var.get()))
        except: self.config["scale_huge_chars"] = DEFAULT_SCALE_HUGE_CHARS

        try: self.config["scale_huge_delay"] = float(self.spin_sc_huge_delay_var.get())
        except: self.config["scale_huge_delay"] = DEFAULT_SCALE_HUGE_DELAY

        try: self.config["max_tags_text_length"] = int(float(self.spin_max_tag_var.get()))
        except: self.config["max_tags_text_length"] = 10000

        self.config["prompt_summary"] = self.txt_p_sum.get("1.0", tk.END).strip()
        self.config["prompt_story"] = self.txt_p_story.get("1.0", tk.END).strip()
        self.config["prompt_tags"] = self.txt_p_tags.get("1.0", tk.END).strip()

        self.config["prompt_forge_full"] = self.txt_p_forge_full.get("1.0", tk.END).strip()
        self.config["prompt_forge_topic"] = self.txt_p_forge_topic.get("1.0", tk.END).strip()
        self.config["prompt_forge_story"] = self.txt_p_forge_story.get("1.0", tk.END).strip()

        self.config["prompt_forge_c1_label"] = self.entry_p_forge_c1_label.get().strip()
        self.config["prompt_forge_c1_prompt"] = self.txt_p_forge_c1_prompt.get("1.0", tk.END).strip()

        self.config["prompt_forge_c2_label"] = self.entry_p_forge_c2_label.get().strip()
        self.config["prompt_forge_c2_prompt"] = self.txt_p_forge_c2_prompt.get("1.0", tk.END).strip()

        self.config["personas"] = self.personas_list

        if self.save_callback:
            self.save_callback()
            messagebox.showinfo("成功", "Accessway 設定 ＆ ペルソナ定義を config.json に保存しました！")


# ================= 🖥️ 単体起動時のテストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("🧠 AiReAccessway 最終修正版テストランナー")
    root.geometry("800x700")

    if os.path.exists(ICON_PORTAL):
        try: root.iconbitmap(ICON_PORTAL)
        except: pass

    def load_cfg():
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    cfg = load_cfg()

    def save_cfg():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    frame = AiReAccesswayFrame(root, cfg, save_cfg)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    root.mainloop()