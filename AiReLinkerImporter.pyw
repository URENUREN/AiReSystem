# -*- coding: utf-8 -*-
# AiReLinkerImporter.pyw - インポーターエントリポイント (ルート配置用)
import os
import sys
import json
import tkinter as tk

try:
    import ctypes
    myappid = 'airelinker.suite.importer.v5_perfect'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
AIRLINKER_DIR = os.path.join(CURRENT_DIR, "AiReLinker")
if AIRLINKER_DIR not in sys.path:
    sys.path.insert(0, AIRLINKER_DIR)

from AiReImporterUI import AiReLinkerImporterFrame, load_config

if __name__ == '__main__':
    root = tk.Tk()
    root.title("🔨 AiReLinkerImporter - チャットログ一括調停インポーター")

    # 🌟 マルチモニター＆全画面独立記憶：設定の読み込み
    cfg = load_config()
    saved_geom = cfg.get("importer_window_geometry", "950x680")
    is_maximized = cfg.get("importer_is_maximized", False)

    # 1. 小ウィンドウ（元に戻した時）の座標をセット
    try:
        root.geometry(saved_geom)
    except:
        root.geometry("950x680")

    # 2. 全画面表示だった場合は zoomed 状態を復元！
    if is_maximized:
        try:
            root.state('zoomed')
        except:
            pass

    app = AiReLinkerImporterFrame(root)
    app.pack(fill="both", expand=True, padx=10, pady=10)
    app.apply_window_icon(root)

    root.mainloop()