# -*- coding: utf-8 -*-
# AiReAPI.py - 3大用途独立マルチ通信エンジン (誤爆防止ロック・2段階テスト・アコーディオンUI対応)
import os
import sys
import json
import threading
import urllib.request
import urllib.error
import urllib.parse
import tkinter as tk
from tkinter import ttk, messagebox

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PORTAL = os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico")

try:
    import ctypes
    myappid = 'airelinker.suite.api.v5'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

class AiReAPIController:
    """🌟 対話・要約・検索の3大用途ごとに独立したAPIサービスを呼び出す通信エンジン"""
    def __init__(self, config):
        self.config = config

    def get_task_config(self, task_type):
        """
        task_type: "chat", "summary", "embedding"
        それぞれの用途で個別に設定された APIプロバイダ / URL / KEY / Model を取得
        """
        api_cfg = self.config.get("api_tasks", {})
        default_gemini = {
            "provider": "Google AI Studio / Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "",
            "model": "gemini-2.0-flash" if task_type == "chat" else ("gemini-2.0-flash-lite" if task_type == "summary" else "text-embedding-004")
        }
        return api_cfg.get(task_type, default_gemini)

    def test_network_ping(self, base_url, log_callback=None):
        """トークンを消費しない【サーバー疎通テスト】（Ping/HTTP接続チェック）"""
        if not base_url:
            if log_callback: log_callback("❌ エラー: ベースURLが空欄です。")
            return False, "ベースURLが入力されていません。"

        if log_callback: log_callback(f"🌐 疎通チェック開始: {base_url}")

        try:
            # http/httpsスキーム補完
            target_url = base_url
            if not target_url.startswith("http://") and not target_url.startswith("https://"):
                target_url = "https://" + target_url

            req = urllib.request.Request(target_url, headers={"User-Agent": "AiReSystem-Ping/1.0"}, method="HEAD")
            try:
                with urllib.request.urlopen(req, timeout=5) as res:
                    code = res.getcode()
                    if log_callback: log_callback(f"✅ 疎通成功 (HTTP ステータス {code})")
                    return True, f"サーバー疎通成功 (HTTP {code})"
            except urllib.error.HTTPError as e_http:
                # 404や401等のレスポンスでも、サーバー自体が存在して応答している証明になる
                if log_callback: log_callback(f"✅ サーバー応答確認 (HTTP ステータス {e_http.code})")
                return True, f"サーバー応答到達 (HTTP {e_http.code})"

        except Exception as e:
            if log_callback: log_callback(f"❌ 疎通失敗: {e}")
            return False, f"サーバーに接続できませんでした: {e}"

    def send_request(self, prompt, system_instruction="", task_type="summary", log_callback=None):
        """テキスト生成（対話・要約）の統一実行メソッド"""
        cfg = self.get_task_config(task_type)
        provider = cfg.get("provider", "Google AI Studio / Gemini")
        base_url = cfg.get("base_url", "").rstrip('/')
        api_key = cfg.get("api_key", "")
        model_name = cfg.get("model", "")

        if log_callback:
            log_callback(f"📡 AIリクエスト送信 [{task_type.upper()}] プロバイダ: {provider} / モデル: {model_name}")

        try:
            # 1. Gemini / Google AI Studio API
            if "gemini" in provider.lower() or "google" in provider.lower():
                if not base_url: base_url = "https://generativelanguage.googleapis.com/v1beta"
                url = f"{base_url}/models/{model_name}:generateContent?key={api_key}"
                
                contents = []
                if system_instruction:
                    contents.append({"role": "user", "parts": [{"text": f"System Instruction: {system_instruction}"}]})
                    contents.append({"role": "model", "parts": [{"text": "Understood."}]})
                contents.append({"role": "user", "parts": [{"text": prompt}]})
                
                payload = {"contents": contents}
                headers = {"Content-Type": "application/json"}
                
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as res:
                    res_data = json.loads(res.read().decode("utf-8"))
                    text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    if log_callback: log_callback(f"✅ レスポンス受信完了 ({len(text)} 文字)")
                    return True, text

            # 2. Claude (Anthropic API)
            elif "claude" in provider.lower() or "anthropic" in provider.lower():
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
                payload = {
                    "model": model_name,
                    "max_tokens": 4000,
                    "system": system_instruction,
                    "messages": [{"role": "user", "content": prompt}]
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as res:
                    res_data = json.loads(res.read().decode("utf-8"))
                    text = res_data["content"][0]["text"]
                    if log_callback: log_callback(f"✅ レスポンス受信完了 ({len(text)} 文字)")
                    return True, text

            # 3. OpenAI 互換 (ChatGPT, Ollama, LM Studio, Jan, その他)
            else:
                if not base_url: base_url = "https://api.openai.com/v1"
                url = f"{base_url}/chat/completions"
                
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                
                payload = {"model": model_name, "messages": messages, "temperature": 0.3}
                headers = {"Content-Type": "application/json"}
                if api_key: headers["Authorization"] = f"Bearer {api_key}"
                    
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as res:
                    res_data = json.loads(res.read().decode("utf-8"))
                    text = res_data["choices"][0]["message"]["content"]
                    if log_callback: log_callback(f"✅ レスポンス受信完了 ({len(text)} 文字)")
                    return True, text

        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8') if e.fp else ""
            if log_callback: log_callback(f"❌ HTTPエラー {e.code}: {err_msg[:120]}")
            return False, f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            if log_callback: log_callback(f"❌ 通信エラー: {e}")
            return False, str(e)

    def get_embedding(self, text, log_callback=None):
        """検索用のテキスト数値ベクトル化（Embedding）統一メソッド"""
        cfg = self.get_task_config("embedding")
        provider = cfg.get("provider", "Google AI Studio / Gemini")
        base_url = cfg.get("base_url", "").rstrip('/')
        api_key = cfg.get("api_key", "")
        model_name = cfg.get("model", "text-embedding-004")

        if log_callback:
            log_callback(f"📡 Vectorリクエスト送信 [EMBEDDING] プロバイダ: {provider} / モデル: {model_name}")

        try:
            if "gemini" in provider.lower() or "google" in provider.lower():
                if not base_url: base_url = "https://generativelanguage.googleapis.com/v1beta"
                url = f"{base_url}/models/{model_name}:embedContent?key={api_key}"
                payload = {"content": {"parts": [{"text": text}]}}
                headers = {"Content-Type": "application/json"}
                
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as res:
                    res_data = json.loads(res.read().decode("utf-8"))
                    vector = res_data["embedding"]["values"]
                    if log_callback: log_callback(f"✅ Vector抽出成功 (次元数: {len(vector)})")
                    return True, vector

            else:
                if not base_url: base_url = "https://api.openai.com/v1"
                url = f"{base_url}/embeddings"
                payload = {"model": model_name, "input": text}
                headers = {"Content-Type": "application/json"}
                if api_key: headers["Authorization"] = f"Bearer {api_key}"

                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as res:
                    res_data = json.loads(res.read().decode("utf-8"))
                    vector = res_data["data"][0]["embedding"]
                    if log_callback: log_callback(f"✅ Vector抽出成功 (次元数: {len(vector)})")
                    return True, vector

        except Exception as e:
            if log_callback: log_callback(f"❌ Embedding抽出エラー: {e}")
            return False, str(e)


class AccordionTaskFrame(ttk.LabelFrame):
    """小スペース折りたたみ（アコーディオン）タスク専用設定フレーム"""
    def __init__(self, parent, task_title, task_key, controller, config, get_lock_status_func, log_func):
        super().__init__(parent, padding=5)
        self.task_title = task_title
        self.task_key = task_key
        self.controller = controller
        self.config = config
        self.get_lock_status = get_lock_status_func
        self.main_log = log_func
        self.is_expanded = False

        self.build_widgets()

    def build_widgets(self):
        # 1. ヘッダー（常に表示されるコンパクトな1行枠）
        header_f = ttk.Frame(self)
        header_f.pack(fill="x", expand=True)

        self.lbl_title = ttk.Label(header_f, text=self.task_title, font=("MS Gothic", 9, "bold"))
        self.lbl_title.pack(side="left", padx=5)

        self.lbl_summary = ttk.Label(header_f, text="[未設定]", font=("MS Gothic", 9), foreground="#555555")
        self.lbl_summary.pack(side="left", padx=10)

        self.btn_toggle = ttk.Button(header_f, text="▶ 詳細展開", width=10, command=self.toggle_expand)
        self.btn_toggle.pack(side="right", padx=5)

        # 2. ボディ（折りたたまれる詳細設定領域）
        self.body_f = ttk.Frame(self, padding=5)

        # プロバイダー
        row0 = ttk.Frame(self.body_f)
        row0.pack(fill="x", pady=2)
        ttk.Label(row0, text="サービス:", width=12).pack(side="left")
        self.provider_var = tk.StringVar(value="Google AI Studio / Gemini")
        combo = ttk.Combobox(
            row0, 
            textvariable=self.provider_var, 
            values=[
                "Google AI Studio / Gemini",
                "OpenAI (ChatGPT)",
                "Claude (Anthropic)",
                "Ollama (ローカルLLM)",
                "LM Studio (ローカルLLM)",
                "Jan / LocalAI (ローカルLLM)",
                "その他 (OpenAI互換カスタム)"
            ], 
            state="readonly", 
            width=25
        )
        combo.pack(side="left", padx=5)
        combo.bind("<<ComboboxSelected>>", self.on_provider_changed)

        # URL
        row1 = ttk.Frame(self.body_f)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="ベースURL:", width=12).pack(side="left")
        self.url_entry = ttk.Entry(row1)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=5)

        # API Key
        row2 = ttk.Frame(self.body_f)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="APIキー:", width=12).pack(side="left")
        self.key_entry = ttk.Entry(row2, show="*")
        self.key_entry.pack(side="left", fill="x", expand=True, padx=5)

        # Model
        row3 = ttk.Frame(self.body_f)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="モデル名:", width=12).pack(side="left")
        self.model_entry = ttk.Entry(row3)
        self.model_entry.pack(side="left", fill="x", expand=True, padx=5)

        # アクションエリア（2段階テストボタン ＆ 注意書き ＆ 個別保存）
        act_f = ttk.Frame(self.body_f)
        act_f.pack(fill="x", pady=6)

        btn_ping = ttk.Button(act_f, text="🌐 疎通テスト(消費0)", command=self.test_ping)
        btn_ping.pack(side="left", padx=2)

        btn_ai = ttk.Button(act_f, text="⚡ AI応答テスト", command=self.test_ai_response)
        btn_ai.pack(side="left", padx=2)

        ttk.Label(act_f, text="ℹ️ ※応答テストは通信枠を1回消費します", font=("MS Gothic", 8), foreground="#d35400").pack(side="left", padx=5)

        btn_save_single = ttk.Button(act_f, text="💾 この設定のみ保存", command=self.save_data_single)
        btn_save_single.pack(side="right", padx=2)

        self.load_data()

    def toggle_expand(self):
        if self.is_expanded:
            self.body_f.pack_forget()
            self.btn_toggle.config(text="▶ 詳細展開")
            self.is_expanded = False
        else:
            self.body_f.pack(fill="x", expand=True, pady=5)
            self.btn_toggle.config(text="▼ 畳む")
            self.is_expanded = True

    def on_provider_changed(self, event=None):
        p = self.provider_var.get()
        if "Google" in p or "Gemini" in p:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, "https://generativelanguage.googleapis.com/v1beta")
            if self.task_key == "embedding": self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "text-embedding-004")
            elif self.task_key == "summary": self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "gemini-2.0-flash-lite")
            else: self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "gemini-2.0-flash")
        elif "OpenAI" in p:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, "https://api.openai.com/v1")
            if self.task_key == "embedding": self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "text-embedding-3-small")
            else: self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "gpt-4o-mini")
        elif "Claude" in p:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, "https://api.anthropic.com/v1")
            self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "claude-3-5-haiku-20241022")
        elif "Ollama" in p:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, "http://localhost:11434/v1")
            if self.task_key == "embedding": self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "bge-m3:latest")
            else: self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "qwen2.5:latest")
        elif "LM Studio" in p:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, "http://localhost:1234/v1")
            self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "local-model")
        elif "Jan" in p:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, "http://localhost:1337/v1")
            self.model_entry.delete(0, tk.END); self.model_entry.insert(0, "local-model")
        self.update_summary_label()

    def update_summary_label(self):
        p = self.provider_var.get()
        m = self.model_entry.get().strip()
        self.lbl_summary.config(text=f"─── [{p}] {m}")

    def load_data(self):
        tasks = self.config.get("api_tasks", {})
        cfg = tasks.get(self.task_key, {})
        self.provider_var.set(cfg.get("provider", "Google AI Studio / Gemini"))
        self.url_entry.delete(0, tk.END); self.url_entry.insert(0, cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta"))
        self.key_entry.delete(0, tk.END); self.key_entry.insert(0, cfg.get("api_key", ""))
        self.model_entry.delete(0, tk.END); self.model_entry.insert(0, cfg.get("model", "gemini-2.0-flash"))
        self.update_summary_label()

    def save_data_single(self):
        tasks = self.config.setdefault("api_tasks", {})
        tasks[self.task_key] = {
            "provider": self.provider_var.get(),
            "base_url": self.url_entry.get().strip(),
            "api_key": self.key_entry.get().strip(),
            "model": self.model_entry.get().strip()
        }
        self.update_summary_label()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("保存成功", f"【{self.task_title}】の設定を個別に保存しました！")
            if self.main_log: self.main_log(f"💾 個別保存完了: {self.task_title}")
        except Exception as e:
            messagebox.showerror("エラー", f"保存失敗: {e}")

    def check_lock_and_alert(self):
        if self.get_lock_status():
            messagebox.showwarning("ロック状態", "🔒 設定・テストがロックされています。\n画面右上にある「🔒 ロック解除」スイッチを切り替えてから実行してください。")
            return True
        return False

    def test_ping(self):
        """トークンを消費しない疎通テスト"""
        if self.check_lock_and_alert(): return
        
        base_url = self.url_entry.get().strip()
        def t():
            success, msg = self.controller.test_network_ping(base_url, self.main_log)
            if success: messagebox.showinfo("疎通成功", f"【{self.task_title}】\nサーバー接続に成功しました！\n({msg})")
            else: messagebox.showerror("疎通失敗", f"【{self.task_title}】\nサーバー応答がありません:\n{msg}")

        threading.Thread(target=t, daemon=True).start()

    def test_ai_response(self):
        """1リクエスト分消費する実AI応答テスト"""
        if self.check_lock_and_alert(): return

        temp_cfg = {
            "provider": self.provider_var.get(),
            "base_url": self.url_entry.get().strip(),
            "api_key": self.key_entry.get().strip(),
            "model": self.model_entry.get().strip()
        }
        
        old_get = self.controller.get_task_config
        self.controller.get_task_config = lambda t: temp_cfg

        def t():
            if self.task_key == "embedding":
                success, res = self.controller.get_embedding("Test text", log_callback=self.main_log)
                msg = f"ベクトル抽出成功 (次元数: {len(res)})" if success else str(res)
            else:
                success, res = self.controller.send_request("Hello. Reply with 'OK'.", task_type=self.task_key, log_callback=self.main_log)
                msg = res

            self.controller.get_task_config = old_get

            if success: messagebox.showinfo("応答成功", f"【{self.task_title}】 AI通信成功！\n応答: {msg}")
            else: messagebox.showerror("応答失敗", f"【{self.task_title}】 AI通信エラー:\n{msg}")

        threading.Thread(target=t, daemon=True).start()


class AiReAPIFrame(ttk.LabelFrame):
    """3大用途別アコーディオン ＆ ロック機能 ＆ リアルタイム通信ログコンソール」コンテナ"""
    def __init__(self, parent, controller, config, save_callback=None):
        super().__init__(parent, text=" 🤖 AI接続設定 (3大用途別アコーディオン管理) ", padding=8)
        self.controller = controller
        self.config = config
        self.save_callback = save_callback

        self.build_widgets()

    def build_widgets(self):
        # ロック解除トグルバー（最右上）
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", pady=2)

        ttk.Label(top_bar, text="💡 用途ごとに異なるAIサービス（Gemini/OpenAI/ローカルLLM等）を独立設定できます。", font=("MS Gothic", 9)).pack(side="left", anchor="w")

        self.is_locked_var = tk.BooleanVar(value=self.config.get("api_is_locked", True))
        
        self.chk_lock = ttk.Checkbutton(
            top_bar, 
            text="🔒 設定・テストロック (誤操作防止)", 
            variable=self.is_locked_var, 
            command=self.on_lock_toggled
        )
        self.chk_lock.pack(side="right", padx=5)

        # 3大用途のアコーディオンフレーム
        self.acc_chat = AccordionTaskFrame(self, "💬 ① AI対話用 (Chat)", "chat", self.controller, self.config, lambda: self.is_locked_var.get(), self.log)
        self.acc_chat.pack(fill="x", pady=3)

        self.acc_sum = AccordionTaskFrame(self, "📝 ② 要約・ストーリー用 (Summary)", "summary", self.controller, self.config, lambda: self.is_locked_var.get(), self.log)
        self.acc_sum.pack(fill="x", pady=3)

        self.acc_embed = AccordionTaskFrame(self, "🔍 ③ 検索・埋め込み用 (Embedding)", "embedding", self.controller, self.config, lambda: self.is_locked_var.get(), self.log)
        self.acc_embed.pack(fill="x", pady=3)

        btn_save_all = ttk.Button(self, text="💾 3大用途の設定をまとめて一括保存", command=self.save_all)
        btn_save_all.pack(anchor="e", pady=4)

        # リアルタイム通信ログコンソール（黒画面復活！）
        log_lf = ttk.LabelFrame(self, text=" 📜 AI通信・テストリアルタイム全般ログ ", padding=5)
        log_lf.pack(fill="both", expand=True, pady=4)

        self.log_text = tk.Text(log_lf, height=6, background="#1e1e1e", foreground="#a0db86", font=("MS Gothic", 9))
        self.log_text.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(log_lf, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.config(state="disabled")

        self.log("システム準備完了: 通信テストおよびAI処理のリアルタイムログがここに表示されます。")

    def log(self, msg):
        """黒い画面へメッセージを書き出す"""
        try:
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, f"[{now}] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")
        except: pass

    def on_lock_toggled(self):
        locked = self.is_locked_var.get()
        self.config["api_is_locked"] = locked
        if locked:
            self.log("🔒 設定・テストロックを 【有効】 にしました。（誤送信を保護します）")
        else:
            self.log("🔓 設定・テストロックを 【解除】 にしました。（編集・テストが可能です）")
        
        if self.save_callback:
            self.save_callback()

    def save_all(self):
        self.acc_chat.save_data_single()
        self.acc_sum.save_data_single()
        self.acc_embed.save_data_single()
        self.config["api_is_locked"] = self.is_locked_var.get()
        if self.save_callback:
            self.save_callback()
            messagebox.showinfo("一括保存成功", "3大用途のAPI設定を config.json に一括保存しました！")


if __name__ == '__main__':
    root = tk.Tk()
    root.title("📡 AiReAPI 決定版 テストランナー")
    root.geometry("700x650")

    def load_cfg():
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    cfg = load_cfg()
    ctrl = AiReAPIController(cfg)

    def save_cfg():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    frame = AiReAPIFrame(root, ctrl, cfg, save_cfg)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    root.mainloop()