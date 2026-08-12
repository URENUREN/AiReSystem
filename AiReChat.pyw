# -*- coding: utf-8 -*-
# AiReChat.pyw - AI対話セッション (年表RAG参照モード・ペルソナ自動連動・厳格上書き保存対応版)
import os
import sys
import json
import re
import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 🌟 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_CHAT = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

# 外部モジュールのインポート
try:
    from AiReAPI import AiReAPIController
    HAS_API = True
except ImportError:
    HAS_API = False

try:
    from AiReAccessway import AiReAccesswayController
    HAS_ACCESSWAY = True
except ImportError:
    HAS_ACCESSWAY = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import ctypes
    myappid = 'airelinker.suite.chat.v4'
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


# デフォルトペルソナ定義（バックアップ用）
DEFAULT_PERSONAS = [
    {
        "id": "standard",
        "name": "標準アシスタント",
        "system_prompt": "あなたは親切で有能なAIアシスタントです。ユーザーの質問に正確で分かりやすく答えてください。"
    },
    {
        "id": "tech_advisor",
        "name": "専門技術顧問・エンジニア",
        "system_prompt": "あなたは経験豊富なシニアソフトウェアエンジニアです。コードの書き方やバグ修正について論理的かつ厳しく指導してください。"
    },
    {
        "id": "kansai_chara",
        "name": "関西弁アシスタント",
        "system_prompt": "あなたは「アイリーちゃん」という名前の明るいパートナーAIです。フランクな関西弁で親しみやすく語りかけてください。"
    }
]


class AiReChatFrame(ttk.Frame):
    """🌟 AI対話セッション GUI フレーム (年表RAG参照・要約/生ログ送信モード切替・厳格上書き保存対応)"""
    def __init__(self, parent, main_app=None):
        super().__init__(parent)
        self.main_app = main_app
        
        if main_app:
            self.config = main_app.config
            self.save_dir = main_app.save_dir
        else:
            self.config = load_config()
            self.save_dir = self.config.get("save_dir", os.path.join(CURRENT_DIR, "logs"))

        self.chat_dir = os.path.join(self.save_dir, "AiReChat")
        os.makedirs(self.chat_dir, exist_ok=True)

        self.api_controller = AiReAPIController(self.config) if HAS_API else None
        self.accessway_ctrl = AiReAccesswayController(self.config, self.save_dir) if HAS_ACCESSWAY else None

        # 会話状態 ＆ 上書き保護管理
        self.current_chat_title = "No Name"
        self.active_session_folder = None # 既存セッションの絶対パス (上書き用)
        self.conversation_history = []    # [{"role": "user"/"model", "text": "..."}]
        self.background_context = ""       # 要約背景データ
        self.raw_context = ""              # 引き継ぎ時の生ログ全文データ
        self.chronicle_context = ""        # 🌟 クロノツリー年表（RAG）テキスト保持用
        self.is_modified = False
        self.is_generating = False

        self._avatar_photo = None
        self.build_ui()
        self.reload_personas_from_config()

    def build_ui(self):
        # 1. 最上部: ヘッダーエリア
        hdr_f = ttk.LabelFrame(self, text=" 🤖 AI対話セッション ＆ ペルソナ設定 ", padding=6)
        hdr_f.pack(fill="x", pady=2, padx=4)

        # アバターアイコン
        self.lbl_avatar = ttk.Label(hdr_f)
        self.lbl_avatar.pack(side="left", padx=4)
        self.load_avatar_icon()

        mid_f = ttk.Frame(hdr_f)
        mid_f.pack(side="left", fill="x", expand=True, padx=4)

        # 1行目: タイトル入力
        row1 = ttk.Frame(mid_f)
        row1.pack(fill="x", pady=1)
        ttk.Label(row1, text="📌 タイトル:", font=("MS Gothic", 9, "bold")).pack(side="left")
        self.entry_title = ttk.Entry(row1, font=("MS Gothic", 9))
        self.entry_title.pack(side="left", fill="x", expand=True, padx=4)
        self.entry_title.insert(0, "")
        self.entry_title.bind("<KeyRelease>", lambda e: self.set_modified(True))

        # 2行目: 🎭 ペルソナ選択 ＆ 🌟 3大文脈モード切替
        row2 = ttk.Frame(mid_f)
        row2.pack(fill="x", pady=1)
        ttk.Label(row2, text="🎭 ペルソナ:", font=("MS Gothic", 9, "bold")).pack(side="left")
        
        self.persona_var = tk.StringVar()
        self.combo_persona = ttk.Combobox(row2, textvariable=self.persona_var, state="readonly", width=14)
        self.combo_persona.pack(side="left", padx=2)

        # 🌟 3大送信文脈モードドロップダウン (要約参照 / 生ログ全文 / 年表RAG参照)
        ttk.Label(row2, text="文脈:", font=("MS Gothic", 8, "bold")).pack(side="left", padx=(4, 1))
        self.context_mode_var = tk.StringVar(value="[1] 背景要約参照")
        self.combo_context_mode = ttk.Combobox(
            row2, 
            textvariable=self.context_mode_var, 
            values=["[1] 背景要約参照", "[2] 生ログ全文参照", "[3] 🗺️ 年表RAG参照"], 
            state="readonly", 
            width=15
        )
        self.combo_context_mode.pack(side="left", padx=2)
        self.combo_context_mode.bind("<<ComboboxSelected>>", self.on_context_mode_changed)

        # 後方互換用チェックボックス参照変数
        self.var_full_context_mode = tk.BooleanVar(value=False)

        self.lbl_status = ttk.Label(row2, text="💡 待機中", font=("MS Gothic", 8), foreground="#555555")
        self.lbl_status.pack(side="left", padx=4)

        # 操作ボタン群
        btn_f = ttk.Frame(hdr_f)
        btn_f.pack(side="right", padx=2)

        ttk.Button(btn_f, text="💾 保存", width=7, command=self.save_chat_session).pack(side="top", pady=1)
        ttk.Button(btn_f, text="📂 復元", width=7, command=self.open_restore_dialog).pack(side="top", pady=1)
        ttk.Button(btn_f, text="🧹 新規", width=7, command=self.start_new_session).pack(side="top", pady=1)

        # 2. ログ表示エリア ＆ 入力欄の PanedWindow
        self.chat_pane = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="#cccccc")
        self.chat_pane.pack(fill="both", expand=True, pady=4, padx=4)

        disp_f = ttk.LabelFrame(self.chat_pane, text=" 💬 会話ログ ", padding=6)
        self.chat_display = tk.Text(disp_f, background="#f8f9fa", font=("MS Gothic", 9), wrap="word")
        self.chat_display.pack(side="left", fill="both", expand=True)

        sb_disp = ttk.Scrollbar(disp_f, command=self.chat_display.yview)
        sb_disp.pack(side="right", fill="y")
        self.chat_display.configure(yscrollcommand=sb_disp.set)

        self.chat_display.tag_config("user_hdr", font=("MS Gothic", 9, "bold"), foreground="#1a73e8", spacing1=8)
        self.chat_display.tag_config("model_hdr", font=("MS Gothic", 9, "bold"), foreground="#2ea44f", spacing1=8)
        self.chat_display.tag_config("sys_hdr", font=("MS Gothic", 8, "italic"), foreground="#8e44ad", spacing1=4)
        self.chat_display.config(state="disabled")

        in_f = ttk.LabelFrame(self.chat_pane, text=" 📝 メッセージ入力 ", padding=6)
        in_txt_f = ttk.Frame(in_f)
        in_txt_f.pack(fill="both", expand=True, pady=2)

        self.txt_input = tk.Text(in_txt_f, height=3, font=("MS Gothic", 9), wrap="word")
        sb_in = ttk.Scrollbar(in_txt_f, command=self.txt_input.yview)
        self.txt_input.configure(yscrollcommand=sb_in.set)

        self.txt_input.pack(side="left", fill="both", expand=True)
        sb_in.pack(side="right", fill="y")

        self.txt_input.bind("<Control-Return>", lambda e: self.send_message())

        act_f = ttk.Frame(in_f)
        act_f.pack(fill="x", pady=(2, 0))
        ttk.Label(act_f, text="💡 [Ctrl + Enter] で送信", font=("MS Gothic", 8), foreground="#7f8c8d").pack(side="left")
        
        self.btn_send = ttk.Button(act_f, text="🚀 送信", command=self.send_message)
        self.btn_send.pack(side="right", padx=2)

        self.chat_pane.add(disp_f, minsize=120, height=350)
        self.chat_pane.add(in_f, minsize=80, height=120)

    def on_context_mode_changed(self, event=None):
        """文脈参照モードが変更された時の表示更新"""
        mode = self.context_mode_var.get()
        if "[2]" in mode or "生ログ" in mode:
            self.var_full_context_mode.set(True)
            self.lbl_status.config(text="📄 生ログ参照", foreground="#0284c7")
        elif "[3]" in mode or "年表" in mode:
            self.var_full_context_mode.set(False)
            self.lbl_status.config(text="🗺️ 年表RAG参照", foreground="#16a34a")
        else:
            self.var_full_context_mode.set(False)
            self.lbl_status.config(text="📝 要約参照", foreground="#555555")

    def reload_personas_from_config(self):
        """🌟 環境設定（personas / chat_personas）のペルソナ定義を自動ロードしてドロップダウンに連動反映"""
        if self.main_app and hasattr(self.main_app, 'config'):
            self.config = self.main_app.config
        else:
            self.config = load_config()

        p_data = self.config.get("personas", self.config.get("chat_personas", DEFAULT_PERSONAS))
        
        self.personas_dict = {}
        if isinstance(p_data, list):
            for item in p_data:
                name = item.get("name", "標準アシスタント")
                prompt = item.get("system_prompt", "")
                self.personas_dict[name] = prompt
        elif isinstance(p_data, dict):
            self.personas_dict = p_data

        if not self.personas_dict:
            self.personas_dict = {"標準アシスタント": "あなたは親切で有能なAIアシスタントです。"}

        names = list(self.personas_dict.keys())
        self.combo_persona["values"] = names
        if names:
            if self.persona_var.get() not in names:
                self.persona_var.set(names[0])

    def load_avatar_icon(self):
        if os.path.exists(ICON_CHAT):
            try:
                if HAS_PIL:
                    img = Image.open(ICON_CHAT)
                    img = img.resize((32, 36), Image.Resampling.LANCZOS)
                    self._avatar_photo = ImageTk.PhotoImage(img)
                    self.lbl_avatar.config(image=self._avatar_photo)
                else: self.lbl_avatar.config(text="🤖")
            except: self.lbl_avatar.config(text="🤖")
        else: self.lbl_avatar.config(text="🤖", font=("Arial", 16))

    def set_modified(self, state=True):
        self.is_modified = state

    def append_display_text(self, role_type, text):
        self.chat_display.config(state="normal")
        now = datetime.datetime.now().strftime("%H:%M")

        if role_type == "user":
            self.chat_display.insert(tk.END, f"\n👤 ユーザー [{now}]:\n", "user_hdr")
        elif role_type == "model":
            self.chat_display.insert(tk.END, f"\n🤖 AI [{now}]:\n", "model_hdr")
        else:
            self.chat_display.insert(tk.END, f"\n⚙️ システム:\n", "sys_hdr")

        self.chat_display.insert(tk.END, f"{text.strip()}\n")
        self.chat_display.see(tk.END)
        self.chat_display.config(state="disabled")

    def send_message(self):
        if self.is_generating or not self.api_controller:
            if not self.api_controller:
                messagebox.showerror("エラー", "AiReAPI モジュールが未ロードです。")
            return

        user_text = self.txt_input.get("1.0", tk.END).strip()
        if not user_text: return

        self.txt_input.delete("1.0", tk.END)

        self.append_display_text("user", user_text)
        self.conversation_history.append({"role": "user", "text": user_text})
        self.set_modified(True)

        self.is_generating = True
        self.btn_send.config(state="disabled")
        self.lbl_status.config(text="⏳ AI応答中...", foreground="#e67e22")

        # ペルソナプロンプトの更新読み込み
        self.reload_personas_from_config()
        selected_p_name = self.persona_var.get()
        sys_inst = self.personas_dict.get(selected_p_name, "あなたは有能なAIアシスタントです。")

        max_turns = self.config.get("chat_max_turns", 10)
        recent_history = self.conversation_history[-max_turns:] if max_turns > 0 else self.conversation_history

        prompt_lines = []

        # 🌟 3大モード分岐: 年表RAG参照 vs 全文生ログ送信 vs 背景要約送信
        mode = self.context_mode_var.get()

        if "[3]" in mode or "年表" in mode:
            if self.chronicle_context:
                prompt_lines.append(
                    f"【📜 クロノツリー全景マップ（開発史年表目次）】\n{self.chronicle_context}\n\n"
                    f"※指示: 上記の年表目次を参照し、ユーザーの質問に関連する過去ログ・成果・仕様・エラー解決を特定して解説してください。"
                    f"回答の末尾には必ず `📌 出典: [該当チャット名/見出し]` を明記してください。\n"
                )
            elif self.background_context:
                prompt_lines.append(
                    f"【📜 参照年表データ】\n{self.background_context}\n\n"
                    f"※指示: 上記の年表・背景データを参照して質問に回答し、回答末尾に `📌 出典: [該当チャット名]` を明記してください。\n"
                )
        elif "[2]" in mode or "生ログ" in mode or self.var_full_context_mode.get():
            if self.raw_context:
                prompt_lines.append(f"【これまでの対話生ログ全文】\n{self.raw_context}\n")
        else:
            if self.background_context:
                prompt_lines.append(f"【これまでの要約・背景コンテキスト】\n{self.background_context}\n")

        prompt_lines.append("【新規対話セッション履歴】")
        for turn in recent_history:
            role_label = "ユーザー" if turn["role"] == "user" else "AI"
            prompt_lines.append(f"{role_label}: {turn['text']}")

        full_prompt = "\n".join(prompt_lines)

        def thread_task():
            ok, res = self.api_controller.send_request(full_prompt, system_instruction=sys_inst, task_type="chat")
            
            def gui_update():
                self.is_generating = False
                self.btn_send.config(state="normal")
                
                if ok:
                    ai_reply = res.strip()
                    if not self.config.get("keep_thought_process", False):
                        ai_reply = re.sub(r'<thought>[\s\S]*?</thought>', '', ai_reply, flags=re.IGNORECASE).strip()

                    self.append_display_text("model", ai_reply)
                    self.conversation_history.append({"role": "model", "text": ai_reply})
                    self.lbl_status.config(text="✅ 応答完了", foreground="#27ae60")
                else:
                    self.append_display_text("system", f"⚠️ 通信エラー:\n{res}")
                    self.lbl_status.config(text="❌ エラー", foreground="#c0392b")

            self.after(0, gui_update)

        threading.Thread(target=thread_task, daemon=True).start()

    def check_unsaved_guard(self):
        if self.is_modified and self.conversation_history:
            title_disp = self.entry_title.get().strip() or "No Name"
            ans = messagebox.askyesnocancel(
                "確認",
                f"進行中の対話セッション『{title_disp}』は保存されていません。\n\n現在の会話を保存しますか？"
            )
            if ans is True:
                return self.save_chat_session()
            elif ans is False:
                return True
            else:
                return False
        return True

    def save_chat_session(self):
        """🌟 厳格な上書き保存 ＆ 新規保存の自動判定分離処理"""
        current_title = self.entry_title.get().strip()

        # タイトル未設定の場合の自動命名
        if not current_title or current_title in ["No Name", "Untitled_Chat"]:
            if self.conversation_history and self.api_controller:
                self.lbl_status.config(text="🧠 AIが自動でタイトル命名中...", foreground="#2980b9")
                first_turn = self.conversation_history[0]["text"][:200]
                ok_t, auto_title = self.api_controller.send_request(
                    f"以下の会話の出だしから、15文字以内の簡潔な日本語タイトルを1つだけ出力してください。\n記号は不要です。\n\n【会話出だし】:\n{first_turn}",
                    task_type="chat"
                )
                if ok_t and auto_title:
                    clean_t = re.sub(r'[\\/*?:"<>|\n\r]', "_", auto_title.strip()).replace("\"", "").replace("'", "")[:20]
                    current_title = clean_t
                else:
                    current_title = "Chat_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            else:
                current_title = "Chat_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            self.entry_title.delete(0, tk.END)
            self.entry_title.insert(0, current_title)

        sanitized_title = re.sub(r'[\\/*?:"<>|]', "_", current_title).strip()

        # 🌟 既存の復元セッションからの保存（上書き）か、新規セッション保存かの厳格判定
        if self.active_session_folder and os.path.exists(self.active_session_folder):
            if os.path.basename(self.active_session_folder) == sanitized_title:
                target_folder = self.active_session_folder
                is_overwrite = True
            else:
                new_folder = os.path.join(self.chat_dir, sanitized_title)
                try:
                    os.rename(self.active_session_folder, new_folder)
                    self.active_session_folder = new_folder
                    target_folder = new_folder
                    is_overwrite = True
                except:
                    target_folder = new_folder
                    is_overwrite = False
        else:
            target_folder = os.path.join(self.chat_dir, sanitized_title)
            is_overwrite = False

        os.makedirs(target_folder, exist_ok=True)
        raw_chat_path = os.path.join(target_folder, "raw_chat.md")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        md_lines = [
            "---",
            'ai_service: "AiReChat"',
            f'processed_turns: {len(self.conversation_history)}',
            f'persona: "{self.persona_var.get()}"',
            f'context_mode: "{self.context_mode_var.get()}"',
            'tags: ["対話セッション"]',
            f'true_start_time: "{now_str}"',
            f'true_end_time: "{now_str}"',
            "---",
            f"\n# 💬 AI対話セッション: {sanitized_title}\n"
        ]

        for turn in self.conversation_history:
            disp_role = "👤 USER" if turn["role"] == "user" else "🤖 MODEL"
            md_lines.append(f"### {disp_role}\n{turn['text']}\n")

        try:
            with open(raw_chat_path, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))

            # 既存セッションパスとして固定
            self.active_session_folder = target_folder
            self.set_modified(False)
            
            msg_type = "上書き更新" if is_overwrite else "新規保存"
            self.lbl_status.config(text=f"💾 {msg_type}完了 ({sanitized_title})", foreground="#27ae60")
            messagebox.showinfo("保存完了", f"対話セッションを{msg_type}しました:\nlogs/AiReChat/{sanitized_title}/raw_chat.md")
            
            if self.main_app and hasattr(self.main_app, 'refresh_portal_data'):
                self.main_app.refresh_portal_data()
            return True
        except Exception as e:
            messagebox.showerror("エラー", f"保存失敗: {e}")
            return False

    def start_new_session(self):
        if not self.check_unsaved_guard(): return

        self.conversation_history.clear()
        self.background_context = ""
        self.raw_context = ""
        self.chronicle_context = ""
        self.active_session_folder = None # セッション保持解除
        self.entry_title.delete(0, tk.END)
        
        self.chat_display.config(state="normal")
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state="disabled")

        self.set_modified(False)
        self.lbl_status.config(text="💡 新規セッション開始", foreground="#555555")

    def load_external_context_and_start(self, context_text, title="引き継ぎ対話", raw_content=""):
        """🌟 ポータル等の外部ログからの引き継ぎ対話の開始"""
        if not self.check_unsaved_guard(): return

        self.start_new_session()
        self.background_context = context_text if context_text else ""
        self.raw_context = raw_content if raw_content else ""
        
        self.entry_title.delete(0, tk.END)
        self.entry_title.insert(0, f"Re_{title}")

        # 画面上に過去発言カードを再現描画
        if raw_content:
            turns = raw_content.split("### ")
            restored_count = 0
            for t_raw in turns[1:]:
                lines = t_raw.strip().split("\n")
                if not lines: continue
                
                header = lines[0].upper()
                role = "user" if ("USER" in header or "ユーザー" in header or "PERSON" in header) else "model"
                body = "\n".join(lines[1:]).strip()
                if body:
                    self.append_display_text(role, body)
                    restored_count += 1
            
            if restored_count > 0:
                self.append_display_text("system", f"📜 過去の対話ログ（{restored_count} ターン）を画面上に描画しました。")

        if self.background_context:
            self.append_display_text("system", f"🧠 背景要約データ（Summary）をAIの文脈記憶としてロードしました。")
        
        self.lbl_status.config(text="🔗 引き継ぎセッション開始", foreground="#2980b9")

    def load_chronicle_rag_context_and_start(self, chronicle_text, title="年表RAG検索対話"):
        """🌟 クロノツリー年表（raw_Chronicle_*.md）を参照データとしてセットし、RAGモードで対話開始"""
        if not self.check_unsaved_guard(): return

        self.start_new_session()
        self.chronicle_context = chronicle_text if chronicle_text else ""
        self.background_context = chronicle_text if chronicle_text else ""
        
        # モードを [3] 年表RAG参照 にセット
        self.context_mode_var.set("[3] 🗺️ 年表RAG参照")
        self.var_full_context_mode.set(False)

        self.entry_title.delete(0, tk.END)
        self.entry_title.insert(0, f"RAG_{title}")

        if self.chronicle_context:
            self.append_display_text(
                "system", 
                f"🗺️ クロノツリー年表（全景マップ）をRAG検索コンテキストとしてロードしました。\n"
                f"(質問を入力すると、AIが年表から該当チャット・仕様を特定し、出典付きで回答します)"
            )

        self.lbl_status.config(text="🗺️ 年表RAG参照モード開始", foreground="#16a34a")

    def open_restore_dialog(self):
        """🌟 AiReChat フォルダ内の過去セッションを完全復元（上書き保存フラグを維持）"""
        if not self.check_unsaved_guard(): return

        if not os.path.exists(self.chat_dir):
            messagebox.showinfo("案内", "復元できる過去の対話セッションが見つかりません。")
            return

        sessions = [f for f in os.listdir(self.chat_dir) if os.path.isdir(os.path.join(self.chat_dir, f))]
        if not sessions:
            messagebox.showinfo("案内", "過去の対話セッションが見つかりません。")
            return

        dlg = tk.Toplevel(self.winfo_toplevel())
        dlg.title("📂 過去の対話セッションを復元")
        dlg.geometry("450x350")

        ttk.Label(dlg, text="復元する対話セッションを選択してください:", font=("MS Gothic", 9, "bold")).pack(anchor="w", padx=10, pady=8)

        lb = tk.Listbox(dlg, selectmode="browse", font=("MS Gothic", 9))
        lb.pack(fill="both", expand=True, padx=10, pady=4)
        for s in sessions: lb.insert(tk.END, f"💬 {s}")

        def do_restore():
            sel = lb.curselection()
            if not sel: return
            target_name = sessions[sel[0]]
            target_folder = os.path.join(self.chat_dir, target_name)
            raw_p = os.path.join(target_folder, "raw_chat.md")

            if os.path.exists(raw_p):
                try:
                    with open(raw_p, "r", encoding="utf-8") as f: content = f.read()
                    
                    self.start_new_session()
                    self.entry_title.delete(0, tk.END)
                    self.entry_title.insert(0, target_name)
                    
                    # 🌟 上書き保存用の既存セッションフォルダとして厳格セット
                    self.active_session_folder = target_folder

                    turns = content.split("### ")
                    for t_raw in turns[1:]:
                        lines = t_raw.strip().split("\n")
                        role = "user" if "USER" in lines[0] else "model"
                        body = "\n".join(lines[1:]).strip()
                        if body:
                            self.append_display_text(role, body)
                            self.conversation_history.append({"role": role, "text": body})

                    self.set_modified(False)
                    self.lbl_status.config(text=f"📂 セッション復元完了 ({target_name})", foreground="#27ae60")
                    dlg.destroy()
                except Exception as e:
                    messagebox.showerror("エラー", f"復元失敗: {e}")

        ttk.Button(dlg, text="🚀 セッションを復元して再開（上書き保存対応）", command=do_restore).pack(fill="x", padx=10, pady=8)


# ================= 🖥️ 単体起動時のテストランナー =================
if __name__ == '__main__':
    root = tk.Tk()
    root.title("💬 AiReChat - 単体対話セッションテスト (年表RAG対応版)")
    root.geometry("480x700")

    if os.path.exists(ICON_CHAT):
        try: root.iconbitmap(ICON_CHAT)
        except: pass

    chat_frame = AiReChatFrame(root, None)
    chat_frame.pack(fill="both", expand=True, padx=8, pady=8)

    def on_closing():
        if chat_frame.check_unsaved_guard():
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()