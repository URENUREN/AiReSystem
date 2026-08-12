# -*- coding: utf-8 -*-
# AiReMediaPlayer.pyw - 高度マルチメディア再生 ＆ 組み込み兼用コンポーネント (マルチスレッド非同期ロード・爆速化版)
import os
import re
import sys
import time
import json
import shutil
import subprocess
import winsound
import threading
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 画像処理 Pillow
try:
    from PIL import Image, ImageTk, ImageSequence
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# 動画処理 OpenCV
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
CONFIG_DIR_MEMORY = os.path.join(CURRENT_DIR, "last_media_dir.json")


def load_last_opened_dir(default_dir):
    if os.path.exists(CONFIG_DIR_MEMORY):
        try:
            with open(CONFIG_DIR_MEMORY, "r", encoding="utf-8") as f:
                data = json.load(f)
                saved_path = data.get("last_dir", "")
                if saved_path and os.path.exists(saved_path):
                    return saved_path
        except: pass
    return default_dir


def save_last_opened_dir(target_filepath):
    if not target_filepath: return
    try:
        dir_path = os.path.dirname(os.path.abspath(target_filepath))
        with open(CONFIG_DIR_MEMORY, "w", encoding="utf-8") as f:
            json.dump({"last_dir": dir_path}, f, indent=4, ensure_ascii=False)
    except: pass


def update_markdown_asset_path(raw_filepath, old_ref, new_ref):
    if not raw_filepath or not os.path.exists(raw_filepath): return False
    try:
        with open(raw_filepath, "r", encoding="utf-8") as f: content = f.read()
        updated_content = content.replace(old_ref, new_ref)
        with open(raw_filepath, "w", encoding="utf-8") as f: f.write(updated_content)
        return True
    except: return False


def unlink_markdown_asset_tag(raw_filepath, target_ref):
    if not raw_filepath or not os.path.exists(raw_filepath): return False
    try:
        with open(raw_filepath, "r", encoding="utf-8") as f: content = f.read()
        fname = os.path.basename(target_ref)
        content = re.sub(r'<(?:video|audio)\s+[^>]*src=["\']' + re.escape(target_ref) + r'["\'][^>]*>(?:</(?:video|audio)>)?', fname, content, flags=re.IGNORECASE)
        content = re.sub(r'!\[.*?\]\(' + re.escape(target_ref) + r'\)', fname, content)
        content = re.sub(r'\[📎\s*添付ファイル:[^\]]+\]\(' + re.escape(target_ref) + r'\)', fname, content)
        if target_ref in content: content = content.replace(target_ref, fname)
        with open(raw_filepath, "w", encoding="utf-8") as f: f.write(content)
        return True
    except: return False


def get_exact_media_duration(filepath):
    """メディア再生時間の同期取得（高速WAV優先）"""
    if not filepath or not os.path.exists(filepath): return 0.0
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == ".wav":
        try:
            import wave
            with wave.open(filepath, 'rb') as wf:
                return wf.getnframes() / float(wf.getframerate())
        except: pass

    try:
        norm_p = os.path.normpath(filepath).replace("\\", "/")
        ps_cmd = (
            f'Add-Type -AssemblyName presentationCore; '
            f'$p = New-Object System.Windows.Media.MediaPlayer; '
            f'$p.Open([System.Uri]"{norm_p}"); '
            f'$i = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $i -lt 20) {{ Start-Sleep -m 50; $i++ }}; '
            f'if ($p.NaturalDuration.HasTimeSpan) {{ Write-Host $p.NaturalDuration.TimeSpan.TotalSeconds }} else {{ Write-Host 0 }}'
        )
        proc = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
        val = float(proc.stdout.strip())
        if val > 0: return val
    except: pass

    return 180.0


def setup_widget_ux_helpers(widget, target_text_widget, cursor_type="arrow"):
    try: widget.config(cursor=cursor_type)
    except: pass

    def on_mouse_wheel(event):
        try: target_text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except: pass
        return "break"

    widget.bind("<MouseWheel>", on_mouse_wheel)


def setup_scale_ux_helpers(scale_widget, on_value_changed_cb, on_release_cb=None, orient="horizontal"):
    def get_ratio_from_event(event):
        if orient == "horizontal":
            width = scale_widget.winfo_width()
            if width <= 0: return 0.0
            return max(0.0, min(1.0, event.x / float(width)))
        else:
            height = scale_widget.winfo_height()
            if height <= 0: return 0.0
            return max(0.0, min(1.0, 1.0 - (event.y / float(height))))

    def on_click(event):
        ratio = get_ratio_from_event(event)
        val = ratio * 100.0
        scale_widget.set(val)
        if on_value_changed_cb: on_value_changed_cb(val)
        return "break"

    def on_drag(event):
        ratio = get_ratio_from_event(event)
        val = ratio * 100.0
        scale_widget.set(val)
        if on_value_changed_cb: on_value_changed_cb(val)
        return "break"

    def on_release(event):
        if on_release_cb: on_release_cb(event)
        return "break"

    scale_widget.bind("<Button-1>", on_click)
    scale_widget.bind("<B1-Motion>", on_drag)
    if on_release_cb: scale_widget.bind("<ButtonRelease-1>", on_release)


class VolumePopupWindow(tk.Toplevel):
    def __init__(self, parent_btn, initial_vol=80, on_volume_change_cb=None):
        super().__init__(parent_btn)
        self.parent_btn = parent_btn
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.on_volume_change_cb = on_volume_change_cb
        
        self.update_idletasks()
        x = parent_btn.winfo_rootx() - 10
        y = parent_btn.winfo_rooty() - 135
        self.geometry(f"45x130+{x}+{y}")
        
        frame = tk.Frame(self, bg="#1e293b", bd=2, relief="ridge")
        frame.pack(fill="both", expand=True)
        
        lbl = tk.Label(frame, text="🔊", bg="#1e293b", fg="white", font=("MS Gothic", 9))
        lbl.pack(side="top", pady=(4, 0))
        
        self.vol_var = tk.DoubleVar(value=initial_vol)
        self.scale = ttk.Scale(frame, from_=100, to=0, orient="vertical", variable=self.vol_var)
        self.scale.pack(fill="y", expand=True, pady=4, padx=6)
        
        setup_scale_ux_helpers(self.scale, on_value_changed_cb=self.on_scale_change, orient="vertical")

        self.parent_btn.is_pop_open = True
        self.bind("<FocusOut>", self.close_pop)
        self.focus_set()

    def on_scale_change(self, val):
        if self.on_volume_change_cb: self.on_volume_change_cb(val)

    def close_pop(self, event=None):
        try:
            self.parent_btn.is_pop_open = False
            self.destroy()
        except: pass


# ================= 🎵 埋め込み型 音声再生カード =================
class InlineAudioPlayerCard(tk.Frame):
    def __init__(self, parent, audio_path, fname, rel_path="", filepath=None, base_dir="", on_update_callback=None, text_widget=None, auto_play=False):
        super().__init__(parent, background="#f8fafc", bd=1, relief="ridge", padx=8, pady=6)
        self.audio_path = audio_path
        self.fname = fname
        self.rel_path = rel_path
        self.filepath = filepath
        self.base_dir = base_dir
        self.on_update_callback = on_update_callback
        self.text_widget = text_widget

        self.is_playing = False
        self.is_dragging_seek = False
        self.volume_val = 80.0
        self.duration_sec = 0.0
        self.start_time = 0.0
        self.pause_offset = 0.0
        self.vol_pop = None
        self.ps_proc = None

        self.build_ui()
        if self.text_widget: setup_widget_ux_helpers(self, self.text_widget)

        # 🌟 時間測定（PowerShell起動）をバックグラウンドスレッドで非同期実行（フリーズ防止！）
        threading.Thread(target=self._async_load_duration, daemon=True).start()

        if auto_play:
            self.after(200, self.toggle_play)

    def _async_load_duration(self):
        dur = get_exact_media_duration(self.audio_path)
        self.duration_sec = dur
        self.after(0, lambda: self.update_time_label(0))

    def build_ui(self):
        hdr_f = tk.Frame(self, bg="#f8fafc")
        hdr_f.pack(fill="x")
        lbl_h = tk.Label(hdr_f, text=f"🎵 音声メディア: {self.fname}", fg="#0284c7", bg="#f8fafc", font=("MS Gothic", 9, "bold"))
        lbl_h.pack(side="left")

        ctrl_f = tk.Frame(self, bg="#f8fafc")
        ctrl_f.pack(fill="x", pady=4)

        self.btn_play = tk.Button(ctrl_f, text="▶ 再生", bg="#0284c7", fg="white", font=("MS Gothic", 8, "bold"), padx=6, command=self.toggle_play)
        self.btn_play.pack(side="left", padx=(0, 5))

        self.lbl_time = tk.Label(ctrl_f, text="00:00 / 00:00", bg="#f8fafc", fg="#64748b", font=("MS Gothic", 8))
        self.lbl_time.pack(side="right", padx=(5, 0))

        self.btn_vol = tk.Button(ctrl_f, text="🔊", bg="#e2e8f0", fg="#0f172a", font=("MS Gothic", 8, "bold"), padx=4, command=self.toggle_volume_popup)
        self.btn_vol.pack(side="right", padx=5)
        self.btn_vol.is_pop_open = False

        self.seek_var = tk.DoubleVar(value=0)
        self.seek_scale = ttk.Scale(ctrl_f, variable=self.seek_var, from_=0, to=100)
        self.seek_scale.pack(side="left", fill="x", expand=True, padx=5)

        setup_scale_ux_helpers(self.seek_scale, on_value_changed_cb=self.on_seek_drag, on_release_cb=self.on_seek_release, orient="horizontal")

        if self.filepath:
            edit_f = tk.Frame(self, bg="#f8fafc")
            edit_f.pack(fill="x", pady=(2, 0))

            btn_ext = tk.Button(edit_f, text="↗ 外部再生", bg="#0369a1", fg="white", font=("MS Gothic", 8), command=self.open_external)
            btn_ext.pack(side="left", padx=2)

            btn_rep = tk.Button(edit_f, text="✏️ 差し替え", bg="#e2e8f0", fg="#334155", font=("MS Gothic", 8), command=self.replace_audio)
            btn_rep.pack(side="right", padx=2)

            btn_del = tk.Button(edit_f, text="🗑️ リンク解除", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8), command=self.delete_audio)
            btn_del.pack(side="right", padx=2)

    def toggle_volume_popup(self):
        if getattr(self.btn_vol, "is_pop_open", False):
            if self.vol_pop:
                self.vol_pop.close_pop()
                self.vol_pop = None
        else:
            self.vol_pop = VolumePopupWindow(self.btn_vol, initial_vol=self.volume_val, on_volume_change_cb=self.set_volume)

    def set_volume(self, val):
        self.volume_val = val
        if self.ps_proc and self.ps_proc.poll() is None:
            try:
                vol_float = val / 100.0
                self.ps_proc.stdin.write(f"$player.Volume = {vol_float}\n")
                self.ps_proc.stdin.flush()
            except: pass

    def start_ps_audio_engine(self):
        if self.ps_proc and self.ps_proc.poll() is None: return
        norm_p = os.path.normpath(self.audio_path).replace("\\", "/")
        vol_float = self.volume_val / 100.0
        ps_script = (
            f'Add-Type -AssemblyName presentationCore; '
            f'$player = New-Object System.Windows.Media.MediaPlayer; '
            f'$player.Open([System.Uri]"{norm_p}"); '
            f'$player.Volume = {vol_float}; '
            f'$player.Position = [System.TimeSpan]::FromSeconds({self.pause_offset}); '
            f'$player.Play(); '
            f'while ($line = [Console]::ReadLine()) {{ Invoke-Expression $line }}'
        )
        try:
            self.ps_proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
        except: pass

    def toggle_play(self):
        if not os.path.exists(self.audio_path):
            messagebox.showwarning("ファイルなし", f"音声ファイルが見つかりません:\n{self.audio_path}")
            return

        if not self.is_playing:
            self.is_playing = True
            try:
                if hasattr(self, 'btn_play') and self.btn_play.winfo_exists():
                    self.btn_play.config(text="⏹ 停止", bg="#dc2626")
            except: pass

            self.start_ps_audio_engine()
            self.start_time = time.time() - self.pause_offset
            self.play_audio_loop()
        else:
            self.stop_audio()

    def stop_audio(self):
        self.is_playing = False
        try:
            if hasattr(self, 'btn_play') and self.btn_play.winfo_exists():
                self.btn_play.config(text="▶ 再生", bg="#0284c7")
        except: pass

        if self.ps_proc:
            try:
                self.ps_proc.terminate()
                self.ps_proc.kill()
                self.ps_proc = None
            except: pass
        self.pause_offset = time.time() - self.start_time

    def on_seek_drag(self, val):
        self.is_dragging_seek = True
        if self.duration_sec > 0:
            target_sec = (float(val) / 100.0) * self.duration_sec
            self.update_time_label(target_sec)

    def on_seek_release(self, event=None):
        self.is_dragging_seek = False
        val = self.seek_var.get()
        if self.duration_sec > 0:
            target_sec = (float(val) / 100.0) * self.duration_sec
            self.pause_offset = target_sec
            self.start_time = time.time() - target_sec

            if self.ps_proc and self.ps_proc.poll() is None:
                try:
                    self.ps_proc.stdin.write(f"$player.Position = [System.TimeSpan]::FromSeconds({target_sec})\n")
                    self.ps_proc.stdin.flush()
                except: pass
            elif self.is_playing:
                self.start_ps_audio_engine()

    def play_audio_loop(self):
        if not self.is_playing: return
        curr_sec = time.time() - self.start_time
        if self.duration_sec > 0:
            if not self.is_dragging_seek:
                try:
                    if hasattr(self, 'seek_var'): self.seek_var.set((curr_sec / self.duration_sec) * 100)
                    self.update_time_label(curr_sec)
                except: pass
            if curr_sec >= self.duration_sec:
                self.stop_audio()
                self.pause_offset = 0
                try:
                    if hasattr(self, 'seek_var'): self.seek_var.set(0)
                except: pass
                return
        try: self.after(100, self.play_audio_loop)
        except: pass

    def update_time_label(self, curr_sec):
        def fmt(s): return f"{int(s) // 60:02d}:{int(s) % 60:02d}"
        try:
            if hasattr(self, 'lbl_time') and self.lbl_time.winfo_exists():
                self.lbl_time.config(text=f"{fmt(curr_sec)} / {fmt(self.duration_sec)}")
        except: pass

    def open_external(self):
        if os.path.exists(self.audio_path):
            try: os.startfile(self.audio_path)
            except Exception as e: messagebox.showerror("再生エラー", f"外部再生失敗: {e}")

    def replace_audio(self):
        initial_search_dir = load_last_opened_dir(self.base_dir)
        new_file = filedialog.askopenfilename(
            title="音声ファイルを差し替え選択（assets/ へ自動格納されます）",
            initialdir=initial_search_dir,
            filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma"), ("All Files", "*.*")]
        )
        if new_file and os.path.exists(new_file):
            save_last_opened_dir(new_file)
            new_fn = os.path.basename(new_file)
            target_dir = os.path.join(self.base_dir, "assets")
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(new_file, os.path.join(target_dir, new_fn))
            
            new_ref = f'<audio src="./assets/{new_fn}" controls></audio>'
            if update_markdown_asset_path(self.filepath, self.rel_path, new_ref):
                if self.on_update_callback: self.on_update_callback()

    def delete_audio(self):
        if messagebox.askyesno("解除確認", f"文章のテキスト・メディア名は保持したまま、アセットリンクを解除しますか？\n({self.fname})"):
            if unlink_markdown_asset_tag(self.filepath, self.rel_path):
                if self.on_update_callback: self.on_update_callback()

    def destroy(self):
        self.stop_audio()
        super().destroy()


# ================= 🎬 埋め込み型 動画再生カード =================
class InlineVideoPlayerCard(tk.Frame):
    def __init__(self, parent, video_path, fname, rel_path="", filepath=None, base_dir="", on_update_callback=None, text_widget=None, auto_play=False, is_standalone=False):
        super().__init__(parent, background="#f1f5f9", bd=1, relief="ridge", padx=8, pady=6)
        self.video_path = video_path
        self.fname = fname
        self.rel_path = rel_path
        self.filepath = filepath
        self.base_dir = base_dir
        self.on_update_callback = on_update_callback
        self.text_widget = text_widget
        self.is_standalone = is_standalone

        self.cap = None
        self.is_playing = False
        self.is_dragging_seek = False
        self.volume_val = 80.0
        self.duration_sec = 0.0
        self.start_time = 0.0
        self.pause_offset = 0.0
        self.fps = 30
        self.total_frames = 0
        self.photo_img = None
        self.vol_pop = None
        self.ps_proc = None
        self.last_frame = None

        self.build_ui()
        if self.text_widget: setup_widget_ux_helpers(self, self.text_widget)
        
        # 🌟 動画オープン ＆ 時間計測を非同期バックグラウンド処理（もっさり防止！）
        threading.Thread(target=self._async_init_video_engine, daemon=True).start()

        if auto_play:
            self.after(200, self.toggle_play)

    def _async_init_video_engine(self):
        """動画オープン・初回コマ取得・時間計算をバックグラウンド実行"""
        if os.path.exists(self.video_path) and HAS_CV2:
            try:
                self.cap = cv2.VideoCapture(self.video_path)
                self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
                self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
                self.duration_sec = self.total_frames / self.fps if self.fps > 0 else 0
                ret, frame = self.cap.read()
                if ret:
                    self.last_frame = frame
                    self.after(0, lambda: self.show_cv2_frame(frame))
                self.after(0, lambda: self.update_time_label(0))
            except: pass

        # 補正でPowerShell時間取得
        if self.duration_sec <= 0:
            dur = get_exact_media_duration(self.video_path)
            self.duration_sec = dur
            self.after(0, lambda: self.update_time_label(0))

    def build_ui(self):
        hdr_f = tk.Frame(self, bg="#f1f5f9")
        hdr_f.pack(fill="x")
        lbl_h = tk.Label(hdr_f, text=f"🎬 動画メディア: {self.fname}", fg="#0d9488", bg="#f1f5f9", font=("MS Gothic", 9, "bold"))
        lbl_h.pack(side="left")

        if self.is_standalone:
            self.canvas = tk.Canvas(self, bg="#000000", highlightthickness=0)
            self.canvas.pack(fill="both", expand=True, pady=4)
            self.canvas.bind("<Configure>", lambda e: self.redraw_last_frame())
        else:
            self.canvas = tk.Canvas(self, width=320, height=240, bg="#000000", highlightthickness=0)
            self.canvas.pack(pady=4)

        ctrl_f = tk.Frame(self, bg="#f1f5f9")
        ctrl_f.pack(fill="x", pady=2, side="bottom")

        self.btn_play = tk.Button(ctrl_f, text="▶ 再生", bg="#0f766e", fg="white", font=("MS Gothic", 8, "bold"), padx=6, command=self.toggle_play)
        self.btn_play.pack(side="left", padx=(0, 5))

        self.lbl_time = tk.Label(ctrl_f, text="00:00 / 00:00", bg="#f1f5f9", fg="#64748b", font=("MS Gothic", 8))
        self.lbl_time.pack(side="right", padx=(5, 0))

        self.btn_vol = tk.Button(ctrl_f, text="🔊", bg="#e2e8f0", fg="#0f172a", font=("MS Gothic", 8, "bold"), padx=4, command=self.toggle_volume_popup)
        self.btn_vol.pack(side="right", padx=5)
        self.btn_vol.is_pop_open = False

        self.seek_var = tk.DoubleVar(value=0)
        self.seek_scale = ttk.Scale(ctrl_f, variable=self.seek_var, from_=0, to=100)
        self.seek_scale.pack(side="left", fill="x", expand=True, padx=5)

        setup_scale_ux_helpers(self.seek_scale, on_value_changed_cb=self.on_seek_drag, on_release_cb=self.on_seek_release, orient="horizontal")

        if self.filepath:
            edit_f = tk.Frame(self, bg="#f1f5f9")
            edit_f.pack(fill="x", pady=(2, 0))

            btn_ext = tk.Button(edit_f, text="↗ 画面再生", bg="#0284c7", fg="white", font=("MS Gothic", 8), command=self.open_external)
            btn_ext.pack(side="left", padx=2)

            btn_rep = tk.Button(edit_f, text="✏️ 差し替え", bg="#e2e8f0", fg="#334155", font=("MS Gothic", 8), command=self.replace_video)
            btn_rep.pack(side="right", padx=2)

            btn_del = tk.Button(edit_f, text="🗑️ リンク解除", bg="#fee2e2", fg="#991b1b", font=("MS Gothic", 8), command=self.delete_video)
            btn_del.pack(side="right", padx=2)

    def redraw_last_frame(self):
        if self.last_frame is not None:
            self.show_cv2_frame(self.last_frame)

    def toggle_volume_popup(self):
        if getattr(self.btn_vol, "is_pop_open", False):
            if self.vol_pop:
                self.vol_pop.close_pop()
                self.vol_pop = None
        else:
            self.vol_pop = VolumePopupWindow(self.btn_vol, initial_vol=self.volume_val, on_volume_change_cb=self.set_volume)

    def set_volume(self, val):
        self.volume_val = val
        if self.ps_proc and self.ps_proc.poll() is None:
            try:
                vol_float = val / 100.0
                self.ps_proc.stdin.write(f"$player.Volume = {vol_float}\n")
                self.ps_proc.stdin.flush()
            except: pass

    def start_ps_audio_engine(self):
        if self.ps_proc and self.ps_proc.poll() is None: return
        norm_p = os.path.normpath(self.video_path).replace("\\", "/")
        vol_float = self.volume_val / 100.0
        ps_script = (
            f'Add-Type -AssemblyName presentationCore; '
            f'$player = New-Object System.Windows.Media.MediaPlayer; '
            f'$player.Open([System.Uri]"{norm_p}"); '
            f'$player.Volume = {vol_float}; '
            f'$player.Position = [System.TimeSpan]::FromSeconds({self.pause_offset}); '
            f'$player.Play(); '
            f'while ($line = [Console]::ReadLine()) {{ Invoke-Expression $line }}'
        )
        try:
            self.ps_proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
        except: pass

    def toggle_play(self):
        if not self.is_playing:
            self.is_playing = True
            try:
                if hasattr(self, 'btn_play') and self.btn_play.winfo_exists():
                    self.btn_play.config(text="⏸ 一時停止", bg="#d97706")
            except: pass

            self.start_ps_audio_engine()
            self.start_time = time.time() - self.pause_offset
            self.play_video_loop()
        else:
            self.pause_media()

    def pause_media(self):
        self.is_playing = False
        try:
            if hasattr(self, 'btn_play') and self.btn_play.winfo_exists():
                self.btn_play.config(text="▶ 再生", bg="#0f766e")
        except: pass

        if self.ps_proc:
            try:
                self.ps_proc.terminate()
                self.ps_proc.kill()
                self.ps_proc = None
            except: pass
        self.pause_offset = time.time() - self.start_time

    def on_seek_drag(self, val):
        self.is_dragging_seek = True
        if self.duration_sec > 0:
            target_sec = (float(val) / 100.0) * self.duration_sec
            self.update_time_label(target_sec)

    def on_seek_release(self, event=None):
        self.is_dragging_seek = False
        val = self.seek_var.get()
        if self.duration_sec > 0:
            target_sec = (float(val) / 100.0) * self.duration_sec
            self.pause_offset = target_sec
            self.start_time = time.time() - target_sec

            if self.ps_proc and self.ps_proc.poll() is None:
                try:
                    self.ps_proc.stdin.write(f"$player.Position = [System.TimeSpan]::FromSeconds({target_sec})\n")
                    self.ps_proc.stdin.flush()
                except: pass
            elif self.is_playing:
                self.start_ps_audio_engine()

            if self.cap and self.total_frames > 0:
                target_f = int((target_sec / self.duration_sec) * self.total_frames)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
                ret, frame = self.cap.read()
                if ret:
                    self.last_frame = frame
                    self.show_cv2_frame(frame)

    def show_cv2_frame(self, frame):
        if not HAS_PIL: return
        try:
            if not hasattr(self, 'canvas') or not self.canvas.winfo_exists(): return
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w <= 10 or h <= 10: w, h = 320, 240

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img.thumbnail((w, h), Image.Resampling.NEAREST)
            self.photo_img = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(w // 2, h // 2, image=self.photo_img, anchor="center")
        except: pass

    def play_video_loop(self):
        if not self.is_playing or not self.cap: return
        elapsed_sec = time.time() - self.start_time
        if self.duration_sec > 0 and elapsed_sec >= self.duration_sec:
            self.pause_media()
            self.pause_offset = 0
            try:
                if hasattr(self, 'seek_var'): self.seek_var.set(0)
            except: pass
            return

        target_frame = int(elapsed_sec * self.fps)
        try: curr_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        except: curr_frame = 0

        if target_frame > curr_frame:
            if target_frame - curr_frame > 5:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = self.cap.read()
            else:
                ret = False
                while curr_frame < target_frame:
                    ret, frame = self.cap.read()
                    curr_frame += 1

            if ret:
                self.last_frame = frame
                self.show_cv2_frame(frame)
                if not self.is_dragging_seek:
                    try:
                        if hasattr(self, 'seek_var'): self.seek_var.set((elapsed_sec / self.duration_sec) * 100)
                        self.update_time_label(elapsed_sec)
                    except: pass

        try: self.after(15, self.play_video_loop)
        except: pass

    def update_time_label(self, curr_sec):
        def fmt(s): return f"{int(s) // 60:02d}:{int(s) % 60:02d}"
        try:
            if hasattr(self, 'lbl_time') and self.lbl_time.winfo_exists():
                self.lbl_time.config(text=f"{fmt(curr_sec)} / {fmt(self.duration_sec)}")
        except: pass

    def open_external(self):
        if os.path.exists(self.video_path):
            try: os.startfile(self.video_path)
            except Exception as e: messagebox.showerror("再生エラー", f"外部再生失敗: {e}")

    def replace_video(self):
        initial_search_dir = load_last_opened_dir(self.base_dir)
        new_file = filedialog.askopenfilename(
            title="動画ファイルを差し替え選択（assets/ へ自動格納されます）",
            initialdir=initial_search_dir,
            filetypes=[("Video Files", "*.mp4 *.webm *.avi *.mov *.wmv *.mkv *.flv"), ("All Files", "*.*")]
        )
        if new_file and os.path.exists(new_file):
            save_last_opened_dir(new_file)
            new_fn = os.path.basename(new_file)
            target_dir = os.path.join(self.base_dir, "assets")
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(new_file, os.path.join(target_dir, new_fn))
            
            new_ref = f'<video src="./assets/{new_fn}" controls width="420"></video>'
            if update_markdown_asset_path(self.filepath, self.rel_path, new_ref):
                if self.on_update_callback: self.on_update_callback()

    def delete_video(self):
        if messagebox.askyesno("解除確認", f"文章のテキスト・メディア名は保持したまま、アセットリンクを解除しますか？\n({self.fname})"):
            if unlink_markdown_asset_tag(self.filepath, self.rel_path):
                if self.on_update_callback: self.on_update_callback()

    def destroy(self):
        self.pause_media()
        if self.cap:
            try: self.cap.release()
            except: pass
        super().destroy()


# ================= 🖼 🎞 アニメーション GIF ＆ .ico 画像表示カード =================
class InlineImageGifPlayerCard(tk.Frame):
    def __init__(self, parent, image_path, fname, rel_path="", filepath=None, base_dir="", is_standalone=False):
        super().__init__(parent, background="#f8fafc", bd=1, relief="ridge", padx=8, pady=6)
        self.image_path = image_path
        self.fname = fname
        self.is_standalone = is_standalone
        self.frames = []
        self.delay = 100
        self.curr_frame_idx = 0
        self.is_playing = True
        self.photo_img = None
        self.last_img = None

        self.build_ui()
        
        # 🌟 GIFコマ分解処理を非同期スレッドロード（描画ブロックを防止！）
        threading.Thread(target=self._async_load_image_or_gif, daemon=True).start()

    def build_ui(self):
        hdr_f = tk.Frame(self, bg="#f8fafc")
        hdr_f.pack(fill="x")
        lbl_h = tk.Label(hdr_f, text=f"🖼️ 画像/GIFアセット: {self.fname}", fg="#7c3aed", bg="#f8fafc", font=("MS Gothic", 9, "bold"))
        lbl_h.pack(side="left")

        if self.is_standalone:
            self.canvas = tk.Canvas(self, bg="#0f172a", highlightthickness=0)
            self.canvas.pack(fill="both", expand=True, pady=4)
            self.canvas.bind("<Configure>", lambda e: self.redraw_last_frame())
        else:
            self.canvas = tk.Canvas(self, width=320, height=240, bg="#0f172a", highlightthickness=0)
            self.canvas.pack(pady=4)

        ctrl_f = tk.Frame(self, bg="#f8fafc")
        ctrl_f.pack(fill="x", pady=2, side="bottom")

        self.btn_play = tk.Button(ctrl_f, text="⏸ 一時停止", bg="#7c3aed", fg="white", font=("MS Gothic", 8, "bold"), padx=6, command=self.toggle_play)
        self.btn_play.pack(side="left")

    def _async_load_image_or_gif(self):
        """アニメーションGIFの全フレーム読み込みをバックグラウンド実行"""
        if not HAS_PIL or not os.path.exists(self.image_path): return
        try:
            img = Image.open(self.image_path)
            if getattr(img, "is_animated", False) and img.n_frames > 1:
                self.delay = img.info.get('duration', 100) or 100
                tmp_frames = []
                for frame in ImageSequence.Iterator(img):
                    tmp_frames.append(frame.copy())
                self.frames = tmp_frames
                self.after(0, lambda: (self.btn_play.pack(side="left"), self.animate_loop()))
            else:
                self.frames = [img.copy()]
                self.after(0, lambda: (self.btn_play.pack_forget(), self.show_frame(self.frames[0])))
        except Exception as e:
            print("GIF/ICO Load error:", e)

    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            try:
                if hasattr(self, 'btn_play') and self.btn_play.winfo_exists():
                    self.btn_play.config(text="▶ 再生", bg="#4c1d95")
            except: pass
        else:
            self.is_playing = True
            try:
                if hasattr(self, 'btn_play') and self.btn_play.winfo_exists():
                    self.btn_play.config(text="⏸ 一時停止", bg="#7c3aed")
            except: pass
            self.animate_loop()

    def redraw_last_frame(self):
        if self.last_img is not None:
            self.show_frame(self.last_img)

    def show_frame(self, pil_img):
        if not HAS_PIL: return
        self.last_img = pil_img
        try:
            if not hasattr(self, 'canvas') or not self.canvas.winfo_exists(): return
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w <= 10 or h <= 10: w, h = 320, 240

            img_copy = pil_img.copy()
            img_copy.thumbnail((w, h), Image.Resampling.NEAREST)
            self.photo_img = ImageTk.PhotoImage(img_copy)
            self.canvas.delete("all")
            self.canvas.create_image(w // 2, h // 2, image=self.photo_img, anchor="center")
        except: pass

    def animate_loop(self):
        if not self.is_playing or not self.frames: return
        frame = self.frames[self.curr_frame_idx]
        self.show_frame(frame)
        self.curr_frame_idx = (self.curr_frame_idx + 1) % len(self.frames)
        try: self.after(self.delay, self.animate_loop)
        except: pass


# ================= 🚀 単体起動 ＆ ポータル組み込み用 メディアプレイヤー画面 =================
class AiReMediaPlayerApp(ttk.Frame):
    def __init__(self, parent, base_dir=None):
        super().__init__(parent, padding=10)
        self.parent = parent
        self.base_dir = base_dir or os.getcwd()
        self.pack(fill="both", expand=True)

        self.media_path = None
        self.media_type = None
        self.active_player_card = None

        self.build_ui()

    def build_ui(self):
        top_f = ttk.LabelFrame(self, text=" 📂 メディアアセット読み込み ", padding=10)
        top_f.pack(fill="x", side="top", pady=(0, 5))

        ttk.Button(
            top_f, text="📂 メディアファイルを開く", 
            command=self.load_media_file
        ).pack(side="left", padx=5)

        self.lbl_file_info = ttk.Label(top_f, text="ファイル未選択", font=("MS Gothic", 9, "bold"))
        self.lbl_file_info.pack(side="left", padx=15)

        self.player_container = ttk.LabelFrame(self, text=" 🎛 インタラクティブメディアプレイヤー ", padding=10)
        self.player_container.pack(fill="both", expand=True, pady=5)

        self.lbl_placeholder = ttk.Label(self.player_container, text="上の「📂 メディアファイルを開く」ボタンから音声・動画・GIF・アイコンを選択してください。", font=("MS Gothic", 10))
        self.lbl_placeholder.pack(expand=True)

    def load_media_file(self):
        initial_dir = load_last_opened_dir(self.base_dir)
        
        path = filedialog.askopenfilename(
            title="メディアファイルを選択 (前回フォルダ位置を自動記憶)", 
            initialdir=initial_dir,
            filetypes=[
                ("All Supported Media", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma *.mp4 *.webm *.avi *.mov *.wmv *.mkv *.flv *.gif *.ico *.png *.jpg *.jpeg"),
                ("Video Files", "*.mp4 *.webm *.avi *.mov *.wmv *.mkv *.flv"),
                ("Audio Files", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma"),
                ("GIF & Image Files", "*.gif *.ico *.png *.jpg *.jpeg"),
                ("All Files", "*.*")
            ]
        )
        if path:
            save_last_opened_dir(path)
            self.play_asset_by_path(path)

    def play_asset_by_path(self, path):
        if not path or not os.path.exists(path): return
        
        video_exts = [".mp4", ".webm", ".avi", ".mov", ".wmv", ".mkv", ".flv"]
        image_exts = [".gif", ".ico", ".png", ".jpg", ".jpeg", ".bmp", ".webp"]
        ext = os.path.splitext(path)[1].lower()

        if ext in video_exts:
            self.mount_video_player(path)
        elif ext in image_exts:
            self.mount_image_gif_player(path)
        else:
            self.mount_audio_player(path)

    def clear_active_player(self):
        if self.active_player_card:
            self.active_player_card.destroy()
            self.active_player_card = None
        self.lbl_placeholder.pack_forget()

    def mount_audio_player(self, path):
        self.clear_active_player()
        fname = os.path.basename(path)
        self.lbl_file_info.config(text=f"🎵 {fname}")
        
        self.active_player_card = InlineAudioPlayerCard(
            parent=self.player_container, audio_path=path, fname=fname, base_dir=self.base_dir, auto_play=True
        )
        self.active_player_card.pack(side="bottom", fill="x", expand=False)

    def mount_video_player(self, path):
        self.clear_active_player()
        fname = os.path.basename(path)
        self.lbl_file_info.config(text=f"🎬 {fname}")

        self.active_player_card = InlineVideoPlayerCard(
            parent=self.player_container, video_path=path, fname=fname, base_dir=self.base_dir, auto_play=True, is_standalone=True
        )
        self.active_player_card.pack(fill="both", expand=True)

    def mount_image_gif_player(self, path):
        self.clear_active_player()
        fname = os.path.basename(path)
        self.lbl_file_info.config(text=f"🖼️ {fname}")

        self.active_player_card = InlineImageGifPlayerCard(
            parent=self.player_container, image_path=path, fname=fname, is_standalone=True
        )
        self.active_player_card.pack(fill="both", expand=True)


if __name__ == '__main__':
    root = tk.Tk()
    root.title("AiReMediaPlayer - 統合マルチメディアエンジン (単体起動モード爆速版)")
    root.geometry("700x560")
    
    def on_exit():
        try:
            if hasattr(app, 'active_player_card') and app.active_player_card:
                app.active_player_card.destroy()
        except: pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_exit)
    app = AiReMediaPlayerApp(root)
    root.mainloop()