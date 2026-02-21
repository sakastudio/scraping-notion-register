# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

**scraping-notion-register**は、Discord Bot経由でWebサイトの記事を自動的にNotionデータベースに登録するシステムです。主にゲーム開発・マーケティング関連の記事を収集・整理するために設計されています。

## 開発コマンド

### 環境セットアップ
```bash
# 仮想環境の作成
python3 -m venv .venv

# 仮想環境のアクティベート
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate      # Windows

# 依存関係のインストール
pip install -r requirements.txt
```

### アプリケーションの実行
```bash
# メインのDiscord Botを起動
python discord_bot.py

# または、start.shスクリプトを使用（依存関係のインストールも含む）
./start.sh
```

### 個別機能のテスト
```bash
# Webスクレイピング機能のテスト
python get_site.py

# Notion登録機能のテスト
python notion_table.py

# タグ予測機能のテスト
python tag_predictor.py

# タイトル翻訳機能のテスト
python title_translator.py
```

## アーキテクチャと構成

### 主要コンポーネント

1. **discord_bot.py** - メインアプリケーション
   - Discord Botのエントリーポイント
   - メッセージ監視とURL検出
   - タスクキューによる非同期処理
   - Keep-aliveサーバーの統合

2. **get_site.py** - Webスクレイピング
   - Firecrawl APIを使用したコンテンツ取得
   - HTML→Markdown変換
   - クッキー認証のサポート（`cookies.json`使用）

3. **notion_table.py** - Notion連携
   - Notionデータベースへのコンテンツ登録
   - 長文コンテンツの分割処理
   - エラーハンドリング

4. **tag_predictor.py** - AI機能（タグ予測）
   - OpenAI GPT-4o-miniを使用
   - `tags.txt`から利用可能なタグを読み込み
   - コンテンツに基づいた自動タグ付け

5. **title_translator.py** - AI機能（翻訳）
   - 非日本語タイトルの自動翻訳
   - OpenAI APIを使用

### データフロー

1. Discord上でURLを含むメッセージを受信
2. URLをタスクキューに追加
3. Firecrawl APIでWebページを取得・変換
4. OpenAI APIでタグ予測とタイトル翻訳
5. Notionデータベースに保存
6. 処理結果をDiscordに通知

### 必要な環境変数

以下の環境変数を`.env`ファイルまたはシステム環境変数に設定：

- `DISCORD_BOT_TOKEN` - Discord Botのトークン
- `NOTION_TOKEN` - Notion APIトークン
- `FIRECRAWL_API_KEY` - Firecrawl APIキー
- `OPENAI_API_KEY` - OpenAI APIキー
- `NOTION_DATABASE_ID` - 保存先のNotionデータベースID
- `DISCORD_CHANNEL_ID` - 監視するDiscordチャンネルID

### 外部ファイル

- **tags.txt** - 利用可能なタグのリスト（83個のタグ）
- **cookies.json** - newsletter.gamediscover.co用の認証クッキー
- **url_list.txt** - テスト用URLリスト

## デプロイ

本番環境はRender（無料プラン）にデプロイされている。mainブランチへのpushで自動デプロイが走る。

### 作業完了後の手順

コード変更をpushしたら、必ずデプロイ結果を確認すること：

```bash
# サービスID確認
render services list --output json

# 最新デプロイのステータス確認（サービスID: srv-d64kkkq4d50c73ehkqfg）
render deploys list srv-d64kkkq4d50c73ehkqfg --output json

# ビルドログ確認（エラー時）
render logs -r srv-d64kkkq4d50c73ehkqfg --output json --type build --limit 100
```

`status` が `live` になれば成功。`build_failed` の場合はログを確認して修正する。

### Render環境の制約

- **root権限なし**: `--with-deps` 等のシステムパッケージインストールは不可
- **メモリ512MB**: 重い処理（Chromium起動等）は注意
- **無料プランの自動スリープ**: keep_aliveサーバーで対策済み

## 開発時の注意点

1. **エラーハンドリング**: 各処理段階でtry-exceptを使用し、エラーをDiscordに通知する設計
2. **非同期処理**: Discord Botはメインスレッド、URL処理はバックグラウンドスレッドで実行
3. **API制限**: OpenAI APIとFirecrawl APIの使用量に注意
4. **Notionの制限**: ブロック数制限（1000ブロック）を考慮した分割処理が実装済み