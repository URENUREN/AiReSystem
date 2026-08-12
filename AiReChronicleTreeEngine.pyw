# -*- coding: utf-8 -*-
# AiReChronicleTreeEngine.pyw - クロノツリー解析エンジン ＆ 右パネルUI (完全スレッド非同期化・フリーズ解消・スライダー整数化版)
import sys
import os
import re
import json
import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# --- 0. ポータブル環境 ＆ ライブラリパス安全設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
embed_site_packages = os.path.join(CURRENT_DIR, "embed-python", "Lib", "site-packages")
if os.path.exists(embed_site_packages) and embed_site_packages not in sys.path:
    sys.path.append(embed_site_packages)

def _setup_tcl_env():
    exe_path = sys.executable.lower()
    if "embed-python" in exe_path:
        embed_dir = os.path.join(CURRENT_DIR, "embed-python")
        search_paths = [
            os.path.join(embed_dir, "tcl"),
            os.path.join(embed_dir, "Lib", "site-packages", "tcl"),
            os.path.join(embed_dir, "Lib", "site-packages", "tkinter_embed"),
        ]
        for sp in search_paths:
            if os.path.exists(sp):
                for root_dir, dirs, files in os.walk(sp):
                    if "init.tcl" in files and "TCL_LIBRARY" not in os.environ:
                        os.environ["TCL_LIBRARY"] = root_dir
                    if "tk.tcl" in files and "TK_LIBRARY" not in os.environ:
                        os.environ["TK_LIBRARY"] = root_dir

_setup_tcl_env()

# --- 1. Janome (形態素解析) インポートチェック ---
HAS_JANOME = False
janome_tokenizer = None
JANOME_ERROR_MSG = ""

try:
    from janome.tokenizer import Tokenizer
    janome_tokenizer = Tokenizer()
    HAS_JANOME = True
except Exception as e:
    HAS_JANOME = False
    JANOME_ERROR_MSG = f"Janome未検出: {e}"


# =========================================================================
# 🧠 1. 純粋解析エンジンクラス (AiReChronicleEngine)
# =========================================================================
class AiReChronicleEngine:
    def __init__(self):
        self.spoken_fillers = [
            r'えーっと', r'あのー', r'ですね', r'でして', r'ございます', r'でしょうか',
            r'と思います', r'かなと思います', r'という風に', r'といった形で', r'ちょっと',
            r'とりあえず', r'一応', r'まあ', r'なんていうか', r'よろしくお願いいたします',
            r'お世話になっております', r'ありがとうございます', r'なっちゃってるんだけどさぁ',
            r'なっちゃってる', r'なんですけど', r'なんですけどさ', r'なっちゃう', r'みたいな感じ',
            r'という感じ', r'な感じで', r'なんだけどさ', r'と思うんだけど', r'っていうか'
        ]

    def _is_japanese(self, text: str) -> bool:
        return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text))

    def _is_code_line(self, line: str) -> bool:
        code_patterns = [
            r'^\s*print\(', r'^\s*import\s', r'^\s*from\s', r'^\s*def\s', r'^\s*class\s',
            r'^\s*self\.', r'^\s*return\s', r'^\s*if\s', r'^\s*elif\s', r'^\s*else:',
            r'^\s*try:', r'^\s*except', r'^\s*messagebox\.', r'^\s*f"[^"]*"', r'^\s*f\'[^\']*\'',
            r'^\s*\{\s*"', r'^\s*"[a-zA-Z0-9_]+"\s*:'
        ]
        return any(re.search(pat, line) for pat in code_patterns)

    def calculate_single_tag_relevance(self, text: str, tag: str) -> float:
        """単一タグの文章内出現密度スコア（0.0〜100.0）を算出"""
        if not tag or not text: return 0.0

        text_lower = text.lower()
        tag_lower = tag.lower()

        count = text_lower.count(tag_lower)
        if count == 0: return 0.0

        char_len = len(text)
        match_char_len = count * len(tag)
        
        density_score = (match_char_len / char_len) * 3000
        hit_bonus = min(50, count * 4)
        
        final_percent = min(99.0, density_score + hit_bonus)
        return round(final_percent, 1)

    def calculate_multi_tag_relevance(self, text: str, tags: list[str]) -> tuple[float, str]:
        """複数選択（アクティブ）タグ群の相乗・ペナルティ加重合成パーセンテージ算出"""
        if not tags or not text:
            return 100.0, "🟢 100%"

        scores = [self.calculate_single_tag_relevance(text, t) for t in tags if t]
        if not scores:
            return 0.0, "⚪ 0%"

        avg_score = sum(scores) / len(scores)
        zero_count = scores.count(0.0)

        if zero_count > 0:
            penalty_factor = (len(scores) - zero_count) / len(scores)
            final_score = avg_score * penalty_factor
        else:
            final_score = min(99.0, avg_score * 1.15) if len(scores) > 1 else avg_score

        final_score = round(final_score, 1)

        if final_score >= 80.0:
            return final_score, f"🟢 {int(final_score)}%"
        elif final_score >= 30.0:
            return final_score, f"🟡 {int(final_score)}%"
        elif final_score >= 1.0:
            return final_score, f"🔴 {int(final_score)}%"
        else:
            return final_score, f"⚪ {int(final_score)}%"

    def _get_word_set(self, text: str) -> set:
        if not HAS_JANOME: return set(list(text))
        try:
            tokens = janome_tokenizer.tokenize(text)
            return set([t.surface for t in tokens if t.part_of_speech.split(',')[0] in ['名詞', '動詞', '形容詞']])
        except:
            return set(list(text))

    def step1_token_compact(self, text: str, compress_level: int = 5) -> tuple[str, str]:
        log_messages = [f"--- [Step 1: TokenCompact 実行] 強度レベル: L{compress_level} ---"]
        lines = text.splitlines()
        compressed_lines = []

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                compressed_lines.append("")
                continue
            if trimmed.startswith('#') or trimmed.startswith('```') or trimmed.startswith('---'):
                compressed_lines.append(trimmed)
                continue
            if self._is_code_line(trimmed) or not self._is_japanese(trimmed):
                compressed_lines.append(trimmed)
                continue

            cleaned_line = trimmed
            if compress_level >= 2:
                for filler in self.spoken_fillers:
                    cleaned_line = re.sub(filler, '', cleaned_line)

            if 3 <= compress_level <= 4:
                cleaned_line = re.sub(r'でございます', 'だ', cleaned_line)
                cleaned_line = re.sub(r'いたします', 'する', cleaned_line)
                cleaned_line = re.sub(r'ください', '', cleaned_line)

            if compress_level >= 5 and HAS_JANOME:
                try:
                    tokens = janome_tokenizer.tokenize(cleaned_line)
                    extracted_words = []
                    for t in tokens:
                        pos_main = t.part_of_speech.split(',')[0]
                        pos_sub = t.part_of_speech.split(',')[1] if len(t.part_of_speech.split(',')) > 1 else ""

                        if pos_main in ['助詞', '助動詞', '接続詞', 'フィラー']:
                            continue

                        if compress_level == 5:
                            if pos_main in ['名詞', '動詞', '形容詞', '副詞', '感動詞', '連体詞', '記号', '未知語']:
                                extracted_words.append(t.surface)
                        elif compress_level == 6:
                            if pos_main in ['名詞', '動詞', '形容詞', '副詞', '未知語']:
                                extracted_words.append(t.surface)
                        elif compress_level == 7:
                            if pos_main in ['名詞', '動詞', '形容詞', '未知語']:
                                extracted_words.append(t.surface)
                        elif compress_level == 8:
                            if pos_main in ['名詞', '未知語']:
                                extracted_words.append(t.surface)
                            elif pos_main in ['動詞', '形容詞']:
                                extracted_words.append(t.base_form)
                        elif compress_level == 9:
                            if pos_main in ['名詞', '未知語']:
                                extracted_words.append(t.surface)
                            elif pos_main == '動詞':
                                extracted_words.append(t.base_form)
                        elif compress_level == 10:
                            if pos_main == '名詞' and pos_sub in ['一般', '固有名詞', 'サ変接続']:
                                extracted_words.append(t.surface)
                            elif pos_main == '動詞':
                                extracted_words.append(t.base_form)

                    cleaned_line = "".join(extracted_words) if extracted_words else cleaned_line
                except Exception as ex:
                    log_messages.append(f"形態素解析エラー: {ex}")

            compressed_lines.append(cleaned_line)

        result_text = "\n".join(compressed_lines)
        ratio = (len(result_text) / len(text) * 100) if len(text) > 0 else 100
        log_messages.append(f"圧縮完了: {len(text):,} ➔ {len(result_text):,} 文字 (圧縮率: {ratio:.1f}%)")
        return result_text, "\n".join(log_messages)

    def step2_cleanse_and_analyze(self, text: str, level: int = 5) -> tuple[str, str]:
        log_messages = [f"--- [Step 2: クレンジング ＆ 分度器解析 実行] 変化点感度: L{level} ---"]
        lines = text.splitlines()
        cleansed_lines = []
        
        shift_threshold_map = {1:0.8, 2:0.7, 3:0.6, 4:0.5, 5:0.4, 6:0.3, 7:0.2, 8:0.15, 9:0.1, 10:0.05}
        shift_threshold = shift_threshold_map.get(level, 0.4)
        loop_keywords = ["エラー", "バグ", "失敗", "直らない", "ダメ", "ループ", "解決しない", "おかしい", "できません"]
        
        current_turn_text = ""
        prev_turn_words = set()
        loop_count = 0
        total_shifts = 0
        removed_count = 0

        for line in lines:
            trimmed = line.strip()
            if not trimmed: continue

            if not self._is_japanese(trimmed) and len(trimmed) > 15 and not trimmed.startswith("http"):
                removed_count += 1
                continue
            if "思考プロセス" in trimmed or "Thinking Process:" in trimmed or "Investigating" in trimmed:
                removed_count += 1
                continue
            if self._is_code_line(trimmed):
                removed_count += 1
                continue

            line_conv = re.sub(r'^(USER|User|ユーザー):', '👤 USER:', trimmed)
            line_conv = re.sub(r'^(MODEL|Model|AI|Assistant):', '🤖 AI:', line_conv)

            if line_conv.startswith("👤 USER:") or line_conv.startswith("🤖 AI:") or line_conv.startswith("### 📄"):
                if current_turn_text:
                    curr_words = self._get_word_set(current_turn_text)
                    if prev_turn_words and curr_words:
                        intersection = len(prev_turn_words.intersection(curr_words))
                        union = len(prev_turn_words.union(curr_words))
                        sim = intersection / union if union > 0 else 0.0

                        is_negative = any(kw in current_turn_text for kw in loop_keywords)
                        if sim >= 0.3 and is_negative:
                            loop_count += 1
                        else:
                            if loop_count >= 2: cleansed_lines.append(f"🔄【LOOP_DETECTED:{loop_count}】")
                            loop_count = 0

                        if sim < shift_threshold:
                            cleansed_lines.append(f"📐【SHIFT_DETECTED:{sim:.2f}】")
                            total_shifts += 1

                    prev_turn_words = curr_words
                current_turn_text = line_conv
            else:
                current_turn_text += " " + line_conv

            cleansed_lines.append(line_conv)

        if loop_count >= 2:
            cleansed_lines.append(f"🔄【LOOP_DETECTED:{loop_count}】")

        log_messages.append(f"ノイズ・英語・コードの除去数: {removed_count:,} 行")
        log_messages.append(f"解析完了: 検出シフト数 {total_shifts} 回 / 閾値: {shift_threshold}")
        return "\n".join(cleansed_lines), "\n".join(log_messages)

    def step3_chrono_tree(self, text: str, level: int = 5) -> tuple[str, str]:
        log_messages = [f"--- [Step 3: ChronoTree 実行] 抽出厳格さレベル: L{level} ---"]
        lines = text.splitlines()

        level_map = {
            1:  (0.50, 500),
            2:  (0.40, 400),
            3:  (0.30, 300),
            4:  (0.25, 200),
            5:  (0.20, 150),
            6:  (0.15, 100),
            7:  (0.10, 80),
            8:  (0.07, 60),
            9:  (0.05, 40),
            10: (0.03, 20)
        }
        base_ratio, cap_max = level_map.get(level, (0.20, 150))

        tree_lines = [
            f"# 📜 開発史クロノツリー全景マップ (生成日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
            "---",
            f"## 📌 チャットセッション別・開発対話要約目次 (厳格さ: L{level} / 基本率: {int(base_ratio*100)}%)",
            ""
        ]

        found_events = 0
        core_keywords = ["結論", "限界", "成功", "解決", "構成", "理由", "マスターログ", "実装", "機能", "エラー", "バグ"]

        chat_blocks = []
        current_block = []
        current_file = "DirectInput"

        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("# 📄 File:") or trimmed.startswith("### 📄"):
                if current_block:
                    chat_blocks.append((current_file, current_block))
                    current_block = []
                current_file = trimmed.replace("# 📄 File:", "").replace("### 📄", "").strip()
            else:
                current_block.append(trimmed)

        if current_block:
            chat_blocks.append((current_file, current_block))

        for file_name, block_lines in chat_blocks:
            tree_lines.append(f"\n### 📁 チャット: {file_name}")
            
            pure_lines = [l for l in block_lines if not l.startswith("📐【") and not l.startswith("🔄【")]
            total_lines = len(pure_lines)
            
            shifts_count = len([l for l in block_lines if l.startswith("📐【SHIFT")])
            loops_count = len([l for l in block_lines if l.startswith("🔄【LOOP")])
            
            dynamic_ratio = base_ratio + (shifts_count * 0.005) + (loops_count * 0.02)
            dynamic_ratio = min(0.80, dynamic_ratio)
            
            max_allowed = max(5, int(total_lines * dynamic_ratio))
            max_allowed = min(cap_max, max_allowed)
            
            file_event_count = 0

            for line in block_lines:
                if not line: continue

                if line.startswith("🔄【LOOP_DETECTED:"):
                    m = re.search(r'LOOP_DETECTED:(\d+)', line)
                    if m:
                        turns = int(m.group(1))
                        tree_lines.append(f"  - 🔄 **【試行錯誤ループ発生】** (類似エラーと再試行を繰り返し、約 {turns} ターンの膠着・足踏みが発生)")
                        found_events += 1
                    continue

                if line.startswith("📐【SHIFT"): continue
                if file_event_count >= max_allowed: continue

                if line.startswith("👤 USER:") or line.startswith("🤖 AI:") or line.startswith("###"):
                    if len(line) > 5 and self._is_japanese(line) and not self._is_code_line(line):
                        tree_lines.append(f"- {line}")
                        found_events += 1
                        file_event_count += 1
                elif any(kw in line for kw in core_keywords):
                    if len(line) > 6 and self._is_japanese(line) and not self._is_code_line(line):
                        tree_lines.append(f"  - {line}")
                        found_events += 1
                        file_event_count += 1

        if found_events == 0:
            tree_lines.append("- *(主要な開発対話トピックが見つかりませんでした)*")

        result_tree = "\n".join(tree_lines)
        log_messages.append(f"抽出完了: イベント数 {found_events:,} 件 / 年表全体 {len(result_tree):,} 文字 (上限キャップ: {cap_max}行)")
        return result_tree, "\n".join(log_messages)


# =========================================================================
# 🖥️ 2. 右パネルUI制御モジュール (ChronicleTreeControlFrame)
# =========================================================================
class ChronicleTreeControlFrame(ttk.Frame):
    def __init__(self, parent, engine_instance, get_source_cb, update_preview_cb, save_vault_cb=None, send_forge_cb=None, send_compass_cb=None):
        super().__init__(parent)
        self.engine = engine_instance
        self.get_source_cb = get_source_cb          
        self.update_preview_cb = update_preview_cb  
        self.save_vault_cb = save_vault_cb          
        self.send_forge_cb = send_forge_cb
        self.send_compass_cb = send_compass_cb

        self.step1_cache = ""
        self.step2_cache = ""
        self.step3_cache = ""

        self.current_preview_step = 0
        self.font_main = ("Yu Gothic UI", 9)
        
        self.action_buttons = [] # 処理中に無効化するボタン群
        
        self.build_ui()

    def build_ui(self):
        self.v_pane = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
        self.v_pane.pack(fill="both", expand=True)

        top_f = ttk.Frame(self.v_pane)
        self.v_pane.add(top_f, minsize=250, height=380)

        exec_lf = ttk.LabelFrame(top_f, text=" ⚡ 3大コアエンジン パラメータ調整 ＆ 実行 ", padding=6)
        exec_lf.pack(fill="both", expand=True, pady=2)

        # --- Step 1 ---
        s1_f = ttk.Frame(exec_lf)
        s1_f.pack(fill="x", pady=4)
        ttk.Label(s1_f, text="🔹 Step 1: 圧縮強度 (TokenCompact)", font=("Yu Gothic UI", 9, "bold")).pack(anchor="w")
        ttk.Label(s1_f, text="(L1: フィラー除去のみ 〜 L10: 名詞・動詞原形のみ極限直結)", font=("Yu Gothic UI", 8), foreground="#64748b").pack(anchor="w")
        
        s1_ctrl = ttk.Frame(s1_f)
        s1_ctrl.pack(fill="x", pady=2)
        self.level_var = tk.IntVar(value=5)
        ttk.Scale(s1_ctrl, from_=1, to=10, variable=self.level_var, orient=tk.HORIZONTAL, command=self._update_s1_scale).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Spinbox(s1_ctrl, from_=1, to=10, textvariable=self.level_var, width=5).pack(side="left", padx=2)
        
        btn_s1 = ttk.Button(s1_ctrl, text="▶ Step 1 実行", command=self.run_step1)
        btn_s1.pack(side="right", padx=2)
        self.action_buttons.append(btn_s1)

        ttk.Separator(exec_lf, orient="horizontal").pack(fill="x", pady=6)

        # --- Step 2 ---
        s2_f = ttk.Frame(exec_lf)
        s2_f.pack(fill="x", pady=4)
        ttk.Label(s2_f, text="🔹 Step 2: 変化点感度 / セマンティック・シフト", font=("Yu Gothic UI", 9, "bold")).pack(anchor="w")
        
        s2_lbl_f = ttk.Frame(s2_f)
        s2_lbl_f.pack(fill="x")
        self.sensitivity_var = tk.IntVar(value=5)
        self.lbl_sens_disp = ttk.Label(s2_lbl_f, text="📐 5 (標準)", font=("Yu Gothic UI", 9), foreground="#0284c7")
        self.lbl_sens_disp.pack(side="left")

        s2_ctrl = ttk.Frame(s2_f)
        s2_ctrl.pack(fill="x", pady=2)
        ttk.Scale(s2_ctrl, from_=1, to=10, variable=self.sensitivity_var, orient=tk.HORIZONTAL, command=self._update_s2_scale).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Spinbox(s2_ctrl, from_=1, to=10, textvariable=self.sensitivity_var, width=5).pack(side="left", padx=2)
        
        btn_s2 = ttk.Button(s2_ctrl, text="▶ Step 2 実行", command=self.run_step2)
        btn_s2.pack(side="right", padx=2)
        self.action_buttons.append(btn_s2)

        ttk.Separator(exec_lf, orient="horizontal").pack(fill="x", pady=6)

        # --- Step 3 ---
        s3_f = ttk.Frame(exec_lf)
        s3_f.pack(fill="x", pady=4)
        ttk.Label(s3_f, text="🔹 Step 3: 年表抽出粒度 (ChronoTree)", font=("Yu Gothic UI", 9, "bold")).pack(anchor="w")
        ttk.Label(s3_f, text="(L1: 詳細・約50%抽出 〜 L10: 極限精選・約3%抽出)", font=("Yu Gothic UI", 8), foreground="#64748b").pack(anchor="w")

        s3_ctrl = ttk.Frame(s3_f)
        s3_ctrl.pack(fill="x", pady=2)
        self.strictness_var = tk.IntVar(value=5)
        ttk.Scale(s3_ctrl, from_=1, to=10, variable=self.strictness_var, orient=tk.HORIZONTAL, command=self._update_s3_scale).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Spinbox(s3_ctrl, from_=1, to=10, textvariable=self.strictness_var, width=5).pack(side="left", padx=2)
        
        btn_s3 = ttk.Button(s3_ctrl, text="▶ Step 3 実行", command=self.run_step3)
        btn_s3.pack(side="right", padx=2)
        self.action_buttons.append(btn_s3)

        # --- 一括実行 ＆ 保存 ---
        act_f = ttk.Frame(exec_lf)
        act_f.pack(fill="x", pady=10)
        
        btn_all = ttk.Button(act_f, text="⚡ 1-3 パイプライン一括実行", command=self.run_all_steps)
        btn_all.pack(fill="x", pady=2)
        self.action_buttons.append(btn_all)

        btn_save = ttk.Button(act_f, text="💾 プレビュー中の状態を任意フォルダへそのまま保存", command=self.save_preview_state)
        btn_save.pack(fill="x", pady=6)
        self.action_buttons.append(btn_save)

        if self.save_vault_cb:
            btn_v = ttk.Button(act_f, text="📦 最終結果を my_RAG_Vault へ一括保存", command=self.trigger_save_vault)
            btn_v.pack(fill="x", pady=2)
            self.action_buttons.append(btn_v)

        if hasattr(self, 'send_forge_cb') and self.send_forge_cb:
            btn_sf = ttk.Button(act_f, text="🔨 選択・圧縮データを Forge タブへ転送", command=self.send_forge_cb)
            btn_sf.pack(fill="x", pady=2)
            self.action_buttons.append(btn_sf)

        if hasattr(self, 'send_compass_cb') and self.send_compass_cb:
            btn_sc = ttk.Button(act_f, text="🧭 選択・圧縮データを Compass タブへ転送", command=self.send_compass_cb)
            btn_sc.pack(fill="x", pady=2)
            self.action_buttons.append(btn_sc)

        # 下部：システムログ＆進捗インジケーター
        bot_f = ttk.Frame(self.v_pane)
        self.v_pane.add(bot_f, minsize=100, height=140)

        log_lf = ttk.LabelFrame(bot_f, text=" 📜 実行ステータス ＆ システムログ ", padding=4)
        log_lf.pack(fill="both", expand=True)

        hdr_f = ttk.Frame(log_lf)
        hdr_f.pack(fill="x", pady=1)
        self.lbl_prog_status = ttk.Label(hdr_f, text="⏳ 待機中...", font=("Yu Gothic UI", 9, "bold"), foreground="#0284c7")
        self.lbl_prog_status.pack(side="left")

        self.log_visible_var = tk.BooleanVar(value=True)
        ttk.Button(hdr_f, text="👁️ 表示/折畳", command=self.toggle_log_visibility, width=12).pack(side="right")

        self.prog_bar = ttk.Progressbar(log_lf, mode="determinate")
        self.prog_bar.pack(fill="x", pady=2)

        self.log_text = tk.Text(log_lf, wrap=tk.WORD, font=("Meiryo", 9), bg="#1E1E1E", fg="#00FF00")
        sb_log = ttk.Scrollbar(log_lf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb_log.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb_log.pack(side="right", fill="y")

    # 🌟 小数点排除！スライダーの完全整数丸め処理
    def _update_s1_scale(self, val):
        self.level_var.set(int(float(val)))

    def _update_s2_scale(self, val):
        v = int(float(val))
        self.sensitivity_var.set(v)
        if v <= 3: lbl = f"📐 L{v} (高感度・詳細)"
        elif v >= 8: lbl = f"📐 L{v} (低感度・大づかみ)"
        else: lbl = f"📐 L{v} (標準)"
        self.lbl_sens_disp.config(text=lbl)

    def _update_s3_scale(self, val):
        self.strictness_var.set(int(float(val)))

    def write_log(self, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{now}] {msg}\n")
        self.log_text.see(tk.END)
        self.update_idletasks()

    def toggle_log_visibility(self):
        if self.log_visible_var.get():
            self.log_text.pack_forget()
            self.log_visible_var.set(False)
        else:
            self.log_text.pack(fill="both", expand=True)
            self.log_visible_var.set(True)

    def _lock_ui(self, msg="⏳ 処理中..."):
        """🌟 処理中にボタンをロックし、インジケーターを動かす（フリーズ解消！）"""
        for btn in self.action_buttons:
            btn.config(state="disabled")
        self.lbl_prog_status.config(text=msg, foreground="#ea580c")
        self.prog_bar.config(mode="indeterminate")
        self.prog_bar.start(15)
        self.update_idletasks()

    def _unlock_ui(self, msg="✅ 完了", val=100, mx=100):
        """🌟 処理完了でロック解除・インジケーター停止"""
        self.prog_bar.stop()
        self.prog_bar.config(mode="determinate", value=val, maximum=mx)
        self.lbl_prog_status.config(text=msg, foreground="#16a34a")
        for btn in self.action_buttons:
            btn.config(state="normal")
        self.update_idletasks()

    # 🌟 各ステップを完全スレッド化し、画面フリーズを根絶！
    def run_step1(self):
        source = self.get_source_cb()
        if not source: return
        self._lock_ui("⏳ [Step 1 圧縮] バックグラウンド実行中...")

        def task():
            try:
                self.step1_cache, log = self.engine.step1_token_compact(source, self.level_var.get())
                self.current_preview_step = 1
                self.after(0, lambda: self.write_log(log))
                self.after(0, lambda: self.update_preview_cb(self.step1_cache, "result"))
                self.after(0, lambda: self._unlock_ui("🎉 Step 1 圧縮完了！"))
            except Exception as e:
                self.after(0, lambda: self._unlock_ui(f"❌ エラー: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def run_step2(self):
        source = self.step1_cache if self.step1_cache else self.get_source_cb()
        if not source: return
        self._lock_ui("⏳ [Step 2 解析] バックグラウンド実行中...")

        def task():
            try:
                self.step2_cache, log = self.engine.step2_cleanse_and_analyze(source, self.sensitivity_var.get())
                self.current_preview_step = 2
                self.after(0, lambda: self.write_log(log))
                self.after(0, lambda: self.update_preview_cb(self.step2_cache, "result"))
                self.after(0, lambda: self._unlock_ui("🎉 Step 2 クレンジング・解析完了！"))
            except Exception as e:
                self.after(0, lambda: self._unlock_ui(f"❌ エラー: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def run_step3(self):
        source = self.step2_cache if self.step2_cache else (self.step1_cache if self.step1_cache else self.get_source_cb())
        if not source: return
        self._lock_ui("⏳ [Step 3 年表化] バックグラウンド実行中...")

        def task():
            try:
                self.step3_cache, log = self.engine.step3_chrono_tree(source, self.strictness_var.get())
                self.current_preview_step = 3
                self.after(0, lambda: self.write_log(log))
                self.after(0, lambda: self.update_preview_cb(self.step3_cache, "result"))
                self.after(0, lambda: self._unlock_ui("🎉 Step 3 動的年表化完了！"))
            except Exception as e:
                self.after(0, lambda: self._unlock_ui(f"❌ エラー: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def run_all_steps(self):
        source = self.get_source_cb()
        if not source: return
        self._lock_ui("⏳ 一括パイプライン処理を開始しています...")
        self.write_log("\n========== ⚡ 一括連動実行開始 ==========")

        def task():
            try:
                self.after(0, lambda: self.lbl_prog_status.config(text="⏳ [Step 1/3] 圧縮処理を実行中..."))
                self.step1_cache, log1 = self.engine.step1_token_compact(source, self.level_var.get())
                self.after(0, lambda: self.write_log(log1))

                self.after(0, lambda: self.lbl_prog_status.config(text="⏳ [Step 2/3] クレンジング ＆ 解析中..."))
                self.step2_cache, log2 = self.engine.step2_cleanse_and_analyze(self.step1_cache, self.sensitivity_var.get())
                self.after(0, lambda: self.write_log(log2))

                self.after(0, lambda: self.lbl_prog_status.config(text="⏳ [Step 3/3] フレキシブル年表化 実行中..."))
                self.step3_cache, log3 = self.engine.step3_chrono_tree(self.step2_cache, self.strictness_var.get())
                self.current_preview_step = 3
                self.after(0, lambda: self.write_log(log3))

                self.after(0, lambda: self.update_preview_cb(self.step3_cache, "result"))
                self.after(0, lambda: self.write_log("========== 🏁 一括処理完了 ==========\n"))
                self.after(0, lambda: self._unlock_ui("🎉 パイプライン処理完了！ (100%)"))
            except Exception as e:
                self.after(0, lambda: self._unlock_ui(f"❌ エラー: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def save_preview_state(self):
        """🌟 プレビュー中の任意ステップ状態を外部フォルダへ保存"""
        content = ""
        if self.current_preview_step == 1: content = self.step1_cache
        elif self.current_preview_step == 2: content = self.step2_cache
        elif self.current_preview_step == 3: content = self.step3_cache

        if not content:
            messagebox.showwarning("警告", "保存するデータがありません。先に実行ボタンを押してください。")
            return

        save_dir = filedialog.askdirectory(title="保存先のフォルダを選択してください")
        if not save_dir: return

        fname = f"AiReChronicle_Step{self.current_preview_step}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        fpath = os.path.join(save_dir, fname)
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("保存完了", f"現在の状態（Step {self.current_preview_step}）を保存しました:\n{fpath}")
            self.write_log(f"💾 任意状態保存完了: {fpath}")
        except Exception as e:
            messagebox.showerror("エラー", f"保存失敗:\n{e}")

    def trigger_save_vault(self):
        if self.save_vault_cb:
            self.save_vault_cb(self.current_preview_step)


# =========================================================================
# 🖥️ 3. スタンドアロンテスト用 GUI
# =========================================================================
class StandaloneTesterGUI(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.raw_text = ""
        self.font_main = ("Yu Gothic UI", 10)
        
        self.engine = AiReChronicleEngine()
        self.build_ui()

        if HAS_JANOME: self.control_frame.write_log("✅ Janome形態素解析エンジン ロード成功。")
        else: self.control_frame.write_log(f"⚠️ {JANOME_ERROR_MSG}")

    def build_ui(self):
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill="both", expand=True, padx=4, pady=4)

        left_p = ttk.LabelFrame(self.main_pane, text=" 📂 テスト入力ソース ", padding=6)
        self.main_pane.add(left_p, weight=1)

        btn_f = ttk.Frame(left_p)
        btn_f.pack(fill="x", pady=2)
        ttk.Button(btn_f, text="📄 単一ファイル読込", command=self.load_file).pack(side="left", padx=2)
        ttk.Button(btn_f, text="📁 フォルダ直下全読込", command=self.load_folder).pack(side="left", padx=2)

        self.input_text = tk.Text(left_p, wrap=tk.WORD, font=("Meiryo", 9))
        self.input_text.pack(fill="both", expand=True, pady=4)

        center_p = ttk.LabelFrame(self.main_pane, text=" 📖 プレビュー結果 ", padding=6)
        self.main_pane.add(center_p, weight=2)
        self.output_text = tk.Text(center_p, wrap=tk.WORD, font=("Meiryo", 9), bg="#F8F9FA")
        self.output_text.pack(fill="both", expand=True)

        right_p = ttk.Frame(self.main_pane, width=320)
        self.main_pane.add(right_p, weight=1)

        self.control_frame = ChronicleTreeControlFrame(
            parent=right_p,
            engine_instance=self.engine,
            get_source_cb=self.get_source_text,
            update_preview_cb=self.update_preview,
            save_vault_cb=self.dummy_save
        )
        self.control_frame.pack(fill="both", expand=True)

    def load_file(self):
        path = filedialog.askopenfilename(title="単一ファイル選択")
        if path:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self.raw_text = f.read()
            self.input_text.delete("1.0", tk.END)
            self.input_text.insert("1.0", self.raw_text)
            self.control_frame.write_log(f"📄 ファイルロード: {os.path.basename(path)}")

    def load_folder(self):
        path = filedialog.askdirectory(title="フォルダ直下全読込")
        if path:
            texts = []
            for f in os.listdir(path):
                if f.endswith(".md"):
                    with open(os.path.join(path, f), "r", encoding="utf-8", errors="ignore") as file:
                        texts.append(f"\n# 📄 File: {f}\n---\n" + file.read())
            self.raw_text = "\n".join(texts)
            self.input_text.delete("1.0", tk.END)
            self.input_text.insert("1.0", self.raw_text)
            self.control_frame.write_log(f"📁 フォルダロード: {len(texts)}件のファイルを結合")

    def get_source_text(self):
        return self.input_text.get("1.0", tk.END).strip()

    def update_preview(self, text, mode):
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", text)

    def dummy_save(self, current_step):
        status_msg = f"現在の表示状態（Step {current_step}）を my_RAG_Vault へ一括保存するテストです。\n本番環境で連携されます。"
        if current_step == 0:
            status_msg = "現在プレビューにデータがありません。保存をキャンセルします。"
        messagebox.showinfo("テスト保存機能", status_msg)


if __name__ == '__main__':
    root = tk.Tk()
    root.title("⚙️ AiReChronicleTree Engine - スタンドアロンテスト環境")
    root.geometry("1100x700")

    app = StandaloneTesterGUI(root)
    app.pack(fill="both", expand=True)

    root.mainloop()