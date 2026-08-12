# ⚓ AiReSystem (AiReAnchor Suite & AiReLinker)
> **〜 失敗・試行錯誤・足踏みの歴史を100%完全保持し、知的資産へ昇華させるローカルナレッジプラットフォーム 〜**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows--10%20%2F%2011-0078D6.svg)]()
[![Architecture](https://img.shields.io/badge/Architecture-Portable%20%2F%20Plugin%20Driven-green.svg)]()
[![License](https://img.shields.io/badge/License-MIT-orange.svg)]()

---

## 📖 目次

1. [システム概要 ＆ 核心コンセプト](#-システム概要--核心コンセプト)
2. [主要機能 ＆ 9大タブ完全操作ガイド](#-主要機能--9大タブ完全操作ガイド)
3. [物理システム構成 ＆ フォルダ構造](#-物理システム構成--フォルダ構造)
4. [セットアップ ＆ 100%ポータブル起動ガイド](#-セットアップ--100ポータブル起動ガイド)
5. [AiReSystem 激闘の開発史（クロノツリー要約）](#-airesystem-激闘の開発史クロノツリー要約)
6. [セキュリティ・隔離ポリシー](#-セキュリティ--隔離ポリシー)
7. [動作要件 ＆ 推奨環境](#-動作要件--推奨環境)

---

## 💡 システム概要 ＆ 核心コンセプト

個人開発やプログラミング、AIとの対話において生じる **「エラー、勘違い、失敗の足踏みループ、試行錯誤の歴史」を消去せずに100%完全保持・蓄積** するローカルナレッジプラットフォーム、それが **AiReSystem** です。

一般的なAIログ保存ツールのように「最終的な成功コード」や「綺麗な要約」だけを残すのではなく、**「どのようにドハマりし、どう解決したか」という泥臭いプロセスそのものを資産化**します。

### 🌟 3大コアテクノロジー
- **📜 クロノツリー（年表目次生成）**: 形態素解析（Janome）と数理アルゴリズムにより、数万文字の対話から試行錯誤の節目を年表化。
- **🧭 年表RAG（目次検索）**: 過去に購入した型番、金額、エラー解決コードを一瞬でピンポイント発掘。
- **🔨 Forge（コンテキスト合成）**: 散らばった複数のチャットから「エラー解決の軌跡」だけを抽出し、次回のAI対話用引き継ぎプロンプトを鋳造。

---

## 🖥️ 主要機能 ＆ 9大タブ完全操作ガイド

AiReSystem は、100%ポータブル動作する9つの物理独立モジュールが1つの大黒柱コンテナ (`AiReAnchorMain.pyw`) にドッキングした構成となっています。

| タブ名称 | モジュールファイル | 役割 ＆ 概要 |
| :--- | :--- | :--- |
| **⚓ AiReAnchorPortal** | `AiReAnchorPortalTab.pyw` | ポータル閲覧・プレビュー・年表RAG連動対話 |
| **📊 AiReAnchorTimeline** | `AiReAnchorTimelineTab.pyw` | DAW（音楽ソフト）風 タイムラインビジュアライザー |
| **🧭 AiReAnchorCompass** | `AiReAnchorCompassTab.pyw` | 高度論理検索 (AND/OR/NOT) ＆ AIベクトル意味検索 |
| **🔨 AiReAnchorForge** | `AiReAnchorForgeTab.pyw` | チャットのコンテキスト切り出し・ワンタッチ結合マージ |
| **📜 AiReChronicleTree** | `AiReChronicleTreeTab.pyw` | 形態素解析による開発史年表（クロノツリー）自動生成 |
| **🎛️ AiReMediaPlayer** | `AiReMediaPlayer.pyw` | ログ内アセット（画像/音声/動画/GIF）の非同期再生 |
| **🔀 AiReLinkageViewer** | `AiReLinkageViewer.pyw` | 新旧対話ログの3パネルDiff比較 ＆ アセット名統合 |
| **📦 AiReLinkerImporter** | `AiReLinkerImporter.pyw` | Google Takeout / Drive 等の一括調停インポーター |
| **⚙️ 環境設定** | `AiReAnchorSettingsTab.pyw` | APIキー設定・カラーテーマ・中継サーバー常駐管理 |

---

### 1. ⚓ AiReAnchorPortal（ポータル閲覧 ＆ 統合プレビュー）
- 左ツリーから保存されたAIサービス別チャットを選択・閲覧。
- 中央のプレビュー画面でMarkdownの簡易装飾・インライン画像描画。
- 右パネルの `AiReChat` により、過去ログの背景文脈（コンテキスト）を維持したまま再対話が可能。

### 2. 📊 AiReAnchorTimeline（DAW風タイムライン）
- DTM/DAWソフトのトラックビューのように、チャットの開始時刻〜最終更新時刻を横軸タイムライン上に可視化。
- トラックの並び替え、ズームイン/ズームアウト、特定トピックの集中観察が可能。

### 3. 🧭 AiReAnchorCompass（ナレッジコンパス / 複合検索）
- 数万行のログから高速で文字検索。
- `AND`, `OR`, `NOT` タグブロックによる直感的な絞り込み検索。
- ローカルLLMやGemini APIを活用した「ベクトル意味検索（RAG）」対応。

### 4. 🔨 AiReAnchorForge（コンテキスト合成ワークスペース）
- 複数チャットの特定トピックや「試行錯誤のエラー解決経緯」だけを抜き出し、新たなMarkdownファイルとして鋳造（Forge）。
- コンテキスト上限（トークン枠）を圧迫せずに次世代のAIチャットへ完璧なバトンタッチが可能。

### 5. 📜 AiReChronicleTree（開発史クロノツリー生成）
- Janome形態素解析を活用し、思考ログや口語表現を自動クレンジング。
- ループ足踏み（「試行錯誤ループ」）を自動検知し、月満ち欠けバッジ (`🌕`, `🌖`, `🌗`) 付きで年表目次を出力。

### 6. 🎛️ AiReMediaPlayer（マルチメディア再生エンジン）
- ログに紐づく画像、GIF、音声 (WAV/MP3)、動画 (MP4/WebM) を非同期ロード。
- カード型描画により画面をフリーズさせずにマルチメディアアセットを閲覧。

### 7. 🔀 AiReLinkageViewer（3パネルDiff比較）
- 新着ログ (`raw_incoming.md`) と本番マスターログ (`raw_scraped.md`) の差分を3パネルで目視比較。
- MD5ハッシュ照合により、重複アセットの排除と自然順タイムラインの自動整列を実行。

### 8. 📦 AiReLinkerImporter（一括調停インポーター）
- Google Takeout (Gemini Apps, Google AI Studio) やドライブの過去ログを一括解析。
- 「総ファイル = 検出チャット + 成功アセット + 迷子アセット」の数学的完全等式に基づき、データ損失ゼロで取り込み。

### 9. ⚙️ 環境設定（システムコントロール）
- Gemini / OpenAI / Local LLM (LM Studio, Ollama) のAPI接続設定およびテスト。
- カラーテーマ切替（クラシック・レトロ ↔ モダン・ライト）。
- `📡 AiReLinker 中継サーバー`（常駐ポート 5000）のワンタッチ起動および表示管理。

---

## 📁 物理システム構成 ＆ フォルダ構造

プロジェクトは拡張性・保守性を極限まで高めた **「完全プラグイン指向・モジュール分離アーキテクチャ」** を採用しています。

```text
D:/program/AiReSystem/
│
├── run.bat                         <-- 🚀 100%ポータブル起動バッチスクリプト
├── AiReAnchorMain.pyw             <-- ⚓ 【大黒柱コンテナ】100%ポータブル起動・エラー監視
├── .gitignore                      <-- 🛡️ Git非公開セキュリティ保護定義
├── config.json.template            <-- 📋 配布用設定テンプレート (config.json に複製して利用)
│
├── 📜 タブUIモジュール群（物理独立・単体動作可能）
│   ├── AiReAnchorPortalTab.pyw     <-- ⚓ ポータル閲覧・プレビュー・年表RAG連動AiReChat
│   ├── AiReAnchorTimelineTab.pyw   <-- 📊 DAW風 タイムラインビジュアライザー
│   ├── AiReAnchorCompassTab.pyw    <-- 🧭 ナレッジコンパス (AND/OR/NOT・マルチスレッド検索)
│   ├── AiReAnchorForgeTab.pyw      <-- 🔨 コンテキスト合成・マージワークスペース
│   ├── AiReChronicleTreeTab.pyw    <-- 📜 開発史クロノツリー年表生成 (月バッジ表示)
│   ├── AiReMediaPlayer.pyw        <-- 🎛 マルチメディア再生エンジン (動画/音声/GIF)
│   ├── AiReLinkageViewer.pyw       <-- 🔀 3パネルDiff比較 ＆ 統括ミニマップ
│   ├── AiReLinkerImporter.pyw      <-- 📦 一括調停インポーター (ルート起動口)
│   └── AiReAnchorSettingsTab.pyw   <-- ⚙️ 3大用途API接続設定 ＆ 常駐コントロール
│
├── 🧠 裏方演算エンジン・通信ドライバー
│   ├── AiReChronicleTreeEngine.pyw <-- 年表極限圧縮 ＆ 変化点/ループ解析エンジン
│   ├── AiReKnots.pyw               <-- 物理統合マスター (raw_master.md) 生成エンジン
│   ├── AiReAccessway.pyw           <-- AIオーケストレーター
│   ├── AiReAPI.pyw                 <-- マルチLLM通信ハブ (Gemini / OpenAI / Local LLM)
│   └── AiReChat.pyw                <-- 🤖 AI対話セッション (年表RAG参照モード搭載)
│
├── 📦 インポーターサブモジュール (`AiReLinker/`)
│   ├── AiReImporterUI.py / AiReImporterLogic.py / AiReImporterDialogs.py / AiReImporterAssets.py
│   └── parsers/ (google_ai_studio.py, gemini_web.py, ai_overviews.py)
│
└── 📁 データ・ポータブル環境
    ├── embed-python/               <-- Python未インストールPC用ポータブル環境 (任意)
    ├── logs/                       <-- ログ格納ルート
    │   ├── my_RAG_Vault/           <-- 生成されたクロノツリー全景マップ保存先
    │   └── my_forge/               <-- Forge合成成果物保存先
    └── icon/                       <-- システム共通アイコンリソース (.ico)