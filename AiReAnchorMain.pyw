# -*- coding: utf-8 -*-
# AiReAnchorMain.pyw - AiReSystem メインエントリーポイント (9大タブ完全ドッキング・潰れ防止＆タブ最適化版)
import os
import sys
import json
import traceback
import urllib.request
import subprocess
import socket
import tkinter as tk
from tkinter import ttk, messagebox

# 🌟 100%ポータブル動的相対パス設定
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")
ICON_PATH = os.path.normpath(os.path.join(CURRENT_DIR, "icon", "AiReAnchor.ico"))

# 🌟 Windows タスクバーアイコン固定用の AppID 登録
try:
    import ctypes
    myappid = 'airelinker.suite.main.v612'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

# 🌟 グローバル・エラーキャッチャー
def global_error_handler(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print("\n" + "="*80, file=sys.stderr)
    print(" [⚠️ SYSTEM ERROR DETECTED] ", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(error_msg, file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)
    
    messagebox.showerror(
        "システムエラー発生", 
        f"プログラム実行中にエラーが発生しました。\n\n"
        f"原因の詳細はターミナルに出力されています。\n\n"
        f"エラー概要: {value}"
    )

sys.excepthook = global_error_handler


class DummyTkWrapper(ttk.Frame):
    def __init__(self, parent_frame):
        super().__init__(parent_frame)
        
    def title(self, *args, **kwargs): pass
    def geometry(self, *args, **kwargs): pass
    def resizable(self, *args, **kwargs): pass
    def protocol(self, *args, **kwargs): pass
    def iconbitmap(self, *args, **kwargs): pass
    def withdraw(self, *args, **kwargs): pass
    def deiconify(self, *args, **kwargs): pass
    def state(self, *args, **kwargs): pass


class AiReAnchorMainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AiReSystem")
        
        # 🌟 1. 潰れバグを根絶する物理最小サイズ制限
        self.root.minsize(1050, 680)
        
        # 🌟 チラつき防止：非表示で初期化
        self.root.withdraw()
        
        self.config = self.load_config()
        
        config_save_dir = self.config.get("save_dir", "")
        if config_save_dir and os.path.exists(config_save_dir):
            self.save_dir = config_save_dir
        else:
            self.save_dir = os.path.join(CURRENT_DIR, "logs")
            
        os.makedirs(self.save_dir, exist_ok=True)

        self.server_was_already_running = False
        self.launched_server_process = None

        # 🌟 2. サブモニター絶対座標の完全復元
        norm_geom = self.config.get("window_normal_geometry", "1300x850+100+100")
        try:
            self.root.geometry(norm_geom)
            self.root.update_idletasks()
            self.root.update()
        except:
            self.root.geometry("1300x850+100+100")

        # 🌟 3. 全画面（最大化）の復元
        is_maximized = self.config.get("window_maximized", False)
        if is_maximized:
            try:
                self.root.state('zoomed')
                self.root.update_idletasks()
                self.root.update()
            except: pass

        self.root.bind("<Configure>", self.on_window_configure)

        self.default_colors = {
            "Gemini": "#2ecc71",
            "AI Studio": "#3498db",
            "Google AI Studio": "#3498db",
            "ChatGPT": "#e74c3c",
            "Claude": "#9b59b6",
            "Local LLM": "#e67e22"
        }
        self.ai_colors = self.config.get("ai_colors", self.default_colors)

        # 🌟 洗練された9大タブ定義（Supporter廃止）
        self.tab_definitions = [
            ("AiReAnchorPortal",   {"bg": "#fce8e6", "fg": "#991b1b", "active": "#dc2626"}),
            ("AiReAnchorTimeline", {"bg": "#fef0d5", "fg": "#9a3412", "active": "#ea580c"}),
            ("AiReAnchorCompass",  {"bg": "#e6f4ea", "fg": "#166534", "active": "#16a34a"}),
            ("AiReAnchorForge",    {"bg": "#f3e8ff", "fg": "#6b21a8", "active": "#9333ea"}),
            ("AiReChronicleTree",  {"bg": "#e0f2fe", "fg": "#0369a1", "active": "#0284c7"}),
            ("AiReMediaPlayer",   {"bg": "#fce4ec", "fg": "#9d174d", "active": "#e11d48"}),
            ("AiReLinkageViewer",  {"bg": "#fffde7", "fg": "#854d0e", "active": "#ca8a04"}),
            ("AiReLinkerImporter", {"bg": "#e0f7fa", "fg": "#155e75", "active": "#0891b2"}),
            ("環境設定",             {"bg": "#f5f5f5", "fg": "#334155", "active": "#0284c7"})
        ]

        # 上部カスタムパステルタブバーコンテナ
        self.tab_bar_frame = tk.Frame(self.root, bg="#d1d5db", height=32)
        self.tab_bar_frame.pack(fill="x", side="top", padx=2, pady=(2, 0))

        # メインコンテンツ表示エリア
        self.content_container = tk.Frame(self.root, bg="#f3f4f6")
        self.content_container.pack(fill="both", expand=True)

        self.tab_buttons = []
        self.tab_frames = []

        # 9つの空フレームの設置
        for _ in range(9):
            f = ttk.Frame(self.content_container)
            self.tab_frames.append(f)

        # 遅延ロードフラグ管理 (9タブ分)
        self.loaded_tab_flags = [False] * 9

        # サブモジュール保持変数
        self.portal_app = None
        self.timeline_app = None
        self.compass_app = None
        self.forge_app = None
        self.chronicle_tree_app = None
        self.media_player_app = None
        self.linkage_viewer_app = None
        self.importer_app = None
        self.settings_app = None

        # パステルボタンの配置
        for idx, (title, color_info) in enumerate(self.tab_definitions):
            btn = tk.Button(
                self.tab_bar_frame,
                text=f" {title} ",
                font=("MS Gothic", 9, "bold"),
                bg=color_info["bg"],
                fg=color_info["fg"],
                activebackground=color_info["bg"],
                activeforeground=color_info["active"],
                bd=1,
                relief="raised",
                cursor="hand2",
                command=lambda i=idx: self.select_tab(i)
            )
            btn.pack(side="left", padx=2, pady=1, fill="y")
            self.tab_buttons.append(btn)

        self.current_tab_idx = 0

        # 超高速起動: ポータルタブ（Index 0）のみを即座にインポート・生成
        self.load_single_tab(0)

        # カラーテーマの適用
        theme_mode = self.config.get("theme_mode", "classic_retro")
        self.apply_theme_style(theme_mode)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 最初のタブ（Portal）を選択・表示
        self.select_tab(0)

        # 超爆速表示
        self.root.deiconify()

        # バックグラウンドで残りのタブを順次ロード開始
        self.root.after(200, lambda: self.start_background_tab_loading(1))

    def load_single_tab(self, idx):
        """🌟 指定されたタブモジュールのみをオンデマンドでインポート＆生成"""
        if self.loaded_tab_flags[idx]:
            return

        frame = self.tab_frames[idx]

        # 0. Portal
        if idx == 0:
            try:
                import AiReAnchorPortalTab
                self.portal_app = AiReAnchorPortalTab.AiReAnchorPortalFrame(frame, self)
                self.portal_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReAnchorPortalTab", e, frame)

        # 1. Timeline
        elif idx == 1:
            try:
                import AiReAnchorTimelineTab
                self.timeline_app = AiReAnchorTimelineTab.AiReAnchorTimelineFrame(frame, self.save_dir, self.ai_colors)
                self.timeline_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReAnchorTimelineTab", e, frame)

        # 2. Compass
        elif idx == 2:
            try:
                import AiReAnchorCompassTab
                self.compass_app = AiReAnchorCompassTab.AiReAnchorCompassFrame(frame, save_dir=self.save_dir, main_app=self)
                self.compass_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReAnchorCompassTab", e, frame)

        # 3. Forge
        elif idx == 3:
            try:
                import AiReAnchorForgeTab
                self.forge_app = AiReAnchorForgeTab.AiReAnchorForgeFrame(frame, save_dir=self.save_dir, main_app=self)
                self.forge_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReAnchorForgeTab", e, frame)

        # 4. ChronicleTree
        elif idx == 4:
            try:
                import AiReChronicleTreeTab
                self.chronicle_tree_app = AiReChronicleTreeTab.AiReChronicleTreeFrame(frame, save_dir=self.save_dir, main_app=self)
                self.chronicle_tree_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReChronicleTreeTab", e, frame)

        # 5. MediaPlayer
        elif idx == 5:
            try:
                import AiReMediaPlayer
                cls_found = getattr(AiReMediaPlayer, "AiReMediaPlayerApp", None)
                if not cls_found:
                    for attr in ["MediaPlayerFrame", "MediaPlayerApp", "AiReMediaPlayerFrame"]:
                        if hasattr(AiReMediaPlayer, attr):
                            cls_found = getattr(AiReMediaPlayer, attr)
                            break

                if cls_found:
                    wrapper = DummyTkWrapper(frame)
                    wrapper.pack(fill="both", expand=True)
                    self.media_player_app = cls_found(wrapper, base_dir=self.save_dir)
                else:
                    self.show_module_error("AiReMediaPlayer", "適合するクラスが見つかりません。", frame)
            except Exception as e:
                self.show_module_error("AiReMediaPlayer", e, frame)

        # 6. LinkageViewer
        elif idx == 6:
            try:
                import AiReLinkageViewer
                cls_found = getattr(AiReLinkageViewer, "AiReLinkageGUI", None)
                if not cls_found:
                    for attr in ["AiReLinkageViewerFrame", "AiReLinkageViewerApp", "AiReLinkageActionDialog"]:
                        if hasattr(AiReLinkageViewer, attr):
                            cls_found = getattr(AiReLinkageViewer, attr)
                            break

                if cls_found:
                    wrapper = DummyTkWrapper(frame)
                    wrapper.pack(fill="both", expand=True)
                    self.linkage_viewer_app = cls_found(wrapper)
                else:
                    self.show_module_error("AiReLinkageViewer", "適合するクラスが見つかりません。", frame)
            except Exception as e:
                self.show_module_error("AiReLinkageViewer", e, frame)

        # 7. Importer
        elif idx == 7:
            try:
                import AiReLinkerImporter
                if hasattr(AiReLinkerImporter, "AiReLinkerImporterFrame"):
                    self.importer_app = AiReLinkerImporter.AiReLinkerImporterFrame(frame, self)
                else:
                    self.importer_app = AiReLinkerImporter.AiReLinkerImporterApp(frame, self)
                self.importer_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReLinkerImporter", e, frame)

        # 8. Settings (Index 8 に移動)
        elif idx == 8:
            try:
                import AiReAnchorSettingsTab
                self.settings_app = AiReAnchorSettingsTab.AiReAnchorSettingsFrame(frame, self)
                self.settings_app.pack(fill="both", expand=True)
            except Exception as e:
                self.show_module_error("AiReAnchorSettingsTab", e, frame)

        self.loaded_tab_flags[idx] = True

    def start_background_tab_loading(self, target_idx):
        """バックグラウンドで残りのタブを順次ロード"""
        if target_idx >= 9:
            return

        if not self.loaded_tab_flags[target_idx]:
            self.load_single_tab(target_idx)

        self.root.after(150, lambda: self.start_background_tab_loading(target_idx + 1))

    def select_tab(self, idx):
        """🌟 タブ切り替え"""
        if not self.loaded_tab_flags[idx]:
            self.load_single_tab(idx)

        self.current_tab_idx = idx

        for f in self.tab_frames:
            f.pack_forget()

        selected_frame = self.tab_frames[idx]
        selected_frame.pack(fill="both", expand=True)

        for i, btn in enumerate(self.tab_buttons):
            color_info = self.tab_definitions[i][1]
            if i == idx:
                btn.config(bg="#ffffff", fg=color_info["active"], relief="sunken", bd=2)
            else:
                btn.config(bg=color_info["bg"], fg=color_info["fg"], relief="raised", bd=1)

        self.root.update_idletasks()

        # インデックス8（Settings）のフィッティング対応
        if idx == 8 and hasattr(self, "settings_app") and self.settings_app:
            if hasattr(self.settings_app, "force_fit_canvas"):
                self.settings_app.force_fit_canvas()

    def apply_theme_style(self, theme_mode="classic_retro"):
        style = ttk.Style()
        if theme_mode == "modern_light":
            try: style.theme_use('vista')
            except:
                try: style.theme_use('xpnative')
                except:
                    try: style.theme_use('default')
                    except: pass
            
            self.tab_bar_frame.config(bg="#cbd5e1")
            self.content_container.config(bg="#ffffff")
        else:
            try: style.theme_use('clam')
            except: pass
            
            self.tab_bar_frame.config(bg="#cbd5e1")
            self.content_container.config(bg="#f1f5f9")

        self.config["theme_mode"] = theme_mode
        self.save_config()

    def on_window_configure(self, event):
        try:
            if event.widget == self.root and self.root.wm_state() == 'normal' and self.root.winfo_viewable():
                geom = self.root.geometry()
                if "x" in geom and ("+" in geom or "-" in geom):
                    self.config["window_normal_geometry"] = geom
        except: pass

    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}

    def save_config(self):
        self.config["ai_colors"] = self.ai_colors
        self.config["save_dir"] = self.save_dir
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except: pass

    def switch_to_forge_with_candidates(self, selected_chat_folders):
        self.config["forge_candidate_chats"] = selected_chat_folders
        self.save_config()

        if not self.loaded_tab_flags[3]:
            self.load_single_tab(3)

        if hasattr(self, "forge_app") and self.forge_app:
            self.forge_app.refresh_chat_tree()

        self.select_tab(3)

    def switch_to_chronicle_with_candidates(self, selected_chat_folders):
        self.config["forge_candidate_chats"] = selected_chat_folders
        self.save_config()

        if not self.loaded_tab_flags[4]:
            self.load_single_tab(4)

        if hasattr(self, "chronicle_tree_app") and self.chronicle_tree_app:
            self.chronicle_tree_app.refresh_chat_tree()

        self.select_tab(4)

    def refresh_portal_data(self):
        if hasattr(self, "portal_app") and self.portal_app and hasattr(self.portal_app, "refresh_portal_data"):
            self.portal_app.refresh_portal_data()
        if hasattr(self, "forge_app") and self.forge_app and hasattr(self.forge_app, "refresh_chat_tree"):
            self.forge_app.refresh_chat_tree()
        if hasattr(self, "chronicle_tree_app") and self.chronicle_tree_app and hasattr(self.chronicle_tree_app, "refresh_chat_tree"):
            self.chronicle_tree_app.refresh_chat_tree()

    def show_module_error(self, module_name, exception, parent_frame):
        err_lbl = ttk.Label(
            parent_frame, 
            text=f"[■] モジュール 『{module_name}』 は合流準備中、または単体動作ファイルです。\n\n"
                 f"※ 他の完成したタブ画面は完全に安全に動作し使うことができます。\n"
                 f"詳細状況: {exception}", 
            justify="center",
            font=("MS Gothic", 10)
        )
        err_lbl.pack(expand=True)

    def on_closing(self):
        try:
            is_max = (self.root.wm_state() == 'zoomed')
            self.config["window_maximized"] = is_max
            
            if not is_max:
                geom = self.root.geometry()
                if "x" in geom and ("+" in geom or "-" in geom):
                    self.config["window_normal_geometry"] = geom

            if hasattr(self, "portal_app") and self.portal_app and hasattr(self.portal_app, "save_portal_state"):
                self.portal_app.save_portal_state()

            self.save_config()
        except: pass

        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()

    if os.path.exists(ICON_PATH):
        try:
            root.iconbitmap(ICON_PATH)
            root.iconbitmap(default=ICON_PATH)
        except: pass

    app = AiReAnchorMainApp(root)
    root.mainloop()