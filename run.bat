@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: カレントディレクトリをスクリプトの存在するパスに固定
cd /d "%~dp0"

echo ============================================================
echo  ⚓ AiReSystem (AiReAnchor Suite) ポータブルランチャー
echo ============================================================
echo.

:: 1. 同梱のポータブルPython (embed-python) を優先検出
if exist "embed-python\pythonw.exe" (
    echo [INFO] ポータブルPython環境 (embed-python) を検出しました。起動します...
    start "" "embed-python\pythonw.exe" "AiReAnchorMain.pyw"
    exit /b
)

if exist "embed-python\python.exe" (
    echo [INFO] ポータブルPython環境 (embed-python) を検出しました。起動します...
    start "" "embed-python\python.exe" "AiReAnchorMain.pyw"
    exit /b
)

:: 2. システム標準の pythonw.exe (コンソール非表示) を検索
where pythonw.exe >nul 2>nul
if !errorlevel! equ 0 (
    echo [INFO] システムの Pythonw 環境を検出しました。起動します...
    start "" pythonw.exe "AiReAnchorMain.pyw"
    exit /b
)

:: 3. システム標準の python.exe を検索
where python.exe >nul 2>nul
if !errorlevel! equ 0 (
    echo [INFO] システムの Python 環境を検出しました。起動します...
    start "" python.exe "AiReAnchorMain.pyw"
    exit /b
)

:: 4. 実行環境が見つからない場合のエラー警告
echo [⚠️ ERROR] 実行に必要な Python 環境が見つかりませんでした。
echo.
echo ■ 対処法:
echo 1. embed-python フォルダをプロジェクト直下に配置する
echo 2. または、Windows に Python (3.10以上推奨) をインストールする
echo.
pause