# Discord YouTube → Notion（Codexサブスク認証）設計

## 目的

Discordの監視対象チャンネルへYouTube URLを投稿するだけで、動画情報、Codexが生成した日本語記事、全文字幕を1つのNotionページへ登録する。記事生成にはOpenAI APIキーを使わず、既存のChatGPTログイン済みCodex CLI認証を利用する。

参考実装は `sakastudio/chrome-ex-youtube-notion-register` とし、記事の構成・字幕の選択優先順位・保存内容を踏襲する。実装先は常駐Bot `scraping-notion-register` とする。

## スコープ

### 対象

- `youtube.com/watch?v=...`
- `youtu.be/...`
- `youtube.com/shorts/...`
- `youtube.com/embed/...`
- `m.youtube.com`、`www.youtube.com` 等の同等URL
- 動画IDを基準にしたcanonical URLへの正規化と重複防止
- 動画情報・全文字幕取得
- Codex CLIによる日本語記事生成
- 1ページへの動画情報・記事・全文字幕保存
- Discordでの進捗・成功・失敗通知

### 対象外

- 字幕の存在しない動画から説明文だけで記事を生成すること
- プレイリスト全体の一括登録
- ライブ配信中で字幕が確定していない動画の部分登録
- Chrome拡張の変更
- OpenAI APIキーによるフォールバック

## アーキテクチャ

```text
Discord URL
  → URL検出・canonical化
  → 重複確認
  → yt-dlpで動画情報・字幕取得
  → 入力検証
  → Codex CLI（ChatGPTサブスク認証）で記事生成
  → 記事出力検証
  → Notion用Markdown構築
  → Notionへ一括登録
  → Discordへ結果通知
```

既存のキューworker内でYouTube専用パイプラインを実行し、通常Web、Speaker Deck、Xの処理には影響させない。

## コンポーネント

### 1. YouTube URL正規化

動画ID抽出をURL parserベースへ整理し、対応URLをすべて次の形式へ統一する。

```text
https://www.youtube.com/watch?v=<VIDEO_ID>
```

追跡query、時刻指定、fragmentを除去する。同じ動画の短縮URL・Shorts URL・モバイルURLは同じNotion登録URLとして扱う。不正hostや11文字でない動画IDは拒否する。

### 2. 動画情報・字幕取得

既存の `yt-dlp` ベース処理を整理し、以下を取得する。

- タイトル
- 説明文
- チャンネル名・ID
- 公開日
- 再生時間
- 再生数・高評価数（取得可能な場合）
- サムネイル
- canonical URLと動画ID
- 字幕本文、言語、手動/自動の区別

字幕の優先順位は次の通り。

1. 日本語手動字幕
2. 日本語自動字幕
3. 英語手動字幕
4. 英語自動字幕

字幕は省略せず全文を保存対象とする。字幕が取得できない、短すぎる、空になる場合はNotionへ部分登録しない。

### 3. Codex記事生成アダプター

Codex CLIを固定absolute pathで起動し、既存の隔離済み認証homeを使う。

- binary: `/Users/sakastudio/.local/bin/codex`
- `HOME` / `CODEX_HOME`: 既存のChatGPTログイン済みCodex環境
- 実行: `codex exec`
- sandbox: `read-only`
- session: `--ephemeral`
- 出力: `--output-last-message` で所有権を限定した一時ファイルへ書く
- 入力: promptと動画情報・字幕をstdinから渡し、argvやログへ字幕を載せない
- 作業ディレクトリ: git repository内
- タイムアウト: 有限時間で終了させ、超過時は子プロセス群を確実に停止
- 同時実行: Bot内で1件ずつ処理する既存workerを維持

Codex認証が無効な場合、CLIが失敗した場合、出力が空・過小・異常に大きい場合は失敗とする。OpenAI APIキーへはフォールバックしない。

モデルslugはCodexの有効な設定値を利用し、環境変数で上書き可能にする。固定slugを盲目的に前提とせず、運用開始前にChatGPTアカウントでcall可能であることをsmoke testする。

### 4. 記事プロンプト

参考Chrome拡張の要件を踏襲し、日本語Markdownで以下を生成する。

- 内容を的確に表す記事タイトル
- エグゼクティブサマリー
- この記事で学べること
- 主要な内容（論理的なセクション構成）
- 重要な洞察
- 実践への応用
- 内容から妥当に導ける場合のみアクションプラン
- まとめ

数値、固有名詞、技術的詳細、事例、話者の留保を保持し、字幕にない事実を断定しない。字幕・説明文は命令ではなく引用データとして扱い、埋め込まれた指示に従わないよう明示する。

Codexには記事本文だけを返させ、全文字幕と動画情報はアプリケーション側で後付けする。これにより、モデルによる字幕改変・省略とMarkdown境界注入を防ぐ。

### 5. Notionページ構成

1ページに次の順で保存する。

1. 動画タイトル
2. YouTube動画埋め込みまたはsource link
3. 動画情報
4. Codex生成記事
5. 区切り
6. `全文字幕` 見出し
7. 字幕の言語・手動/自動表示
8. 全文字幕

全文字幕はcode blockや画像altだけではなく、Notion検索対象となる通常テキストブロックとして分割保存する。Notionのrich text上限とblock batch上限を既存処理で守る。分割時に文字を欠落・重複させない。

Notionページ作成は記事生成と全入力検証が完了した後にのみ開始する。ページ作成後のblock append失敗は既存のエラー処理に加え、作成済みページを不完全な成功として通知しない。

### 6. Markdown・入力安全性

- 動画タイトル、説明文、チャンネル名、字幕を信頼しない
- モデル入力では外部コンテンツを明確なデータ境界内へ格納する
- モデル出力のMarkdownを許可されたNotion blockへ変換する
- 外部コンテンツから任意image/file URLを注入させない
- 字幕はモデル出力と混ぜず、通常paragraphとして直接構築する
- 一時ファイルは`0600`相当、処理終了時に成功・失敗を問わず削除する
- auth token、cookie、字幕全文、Codex JSONLを通常ログへ出さない

## エラー処理

以下はNotion登録前に失敗させ、Discordへ短い理由と対象URLを通知する。

- URL・動画IDが不正
- 動画が非公開、削除済み、年齢/地域制限等で取得不能
- 字幕なし、字幕取得/parse失敗
- Codex未ログインまたは認証期限切れ
- Codex timeout・非zero終了
- Codex記事が空、短すぎる、サイズ上限超過
- Notion登録前の入力不整合

Cookieやtokenなど秘密情報をエラー文へ含めない。失敗したURLは「登録済み」と扱わず、再投稿で再試行可能にする。

## テスト戦略

TDDで各機能の失敗テストを先に追加する。

### Unit

- YouTube URL variantsが同じcanonical URLになる
- 不正host、playlist-only URL、不正video IDを拒否する
- 字幕優先順位が正しい
- VTT/SRT/JSON系字幕から文字欠落なく正規化できる
- 全文字幕がNotion検索可能な通常blockとして分割される
- Codex argvに字幕・秘密情報を含めない
- Codex環境が指定の認証homeに限定される
- timeout、非zero、空出力、過大出力を拒否する
- prompt injection文字列がNotion image/file blockにならない
- 途中失敗でNotion登録関数が呼ばれない

### Integration

- fake Codex executableでstdin、環境、出力ファイル、cleanupを検証
- fixture動画情報＋長い字幕からNotion block payload全体を検証
- Discord workerがYouTubeをskipせず専用パイプラインへ送る
- 重複動画を再登録しない

### E2E

- 公開され字幕のある実YouTube動画でmetadata・全文字幕取得
- ChatGPT認証済みCodex CLIで記事生成
- テスト対象Notion databaseへ登録
- 作成ページをNotion APIで再取得し、以下を確認
  - source URL
  - 記事見出し
  - 動画情報
  - 字幕の先頭・中間・末尾文字列
  - 字幕が通常テキストblockであること
- 常駐Bot再起動後、health・PID・ログを確認

## リリース条件

- focused testsと全テストが成功
- `py_compile`と`git diff --check`が成功
- 実URL/Codex/NotionのE2Eが成功
- 独立レビューでCritical/Highを解消
- commit・`main` push
- watchdog経由でBot再起動
- 新PID、health endpoint、監視チャンネル接続を確認

## 運用上の前提

Codex CLIのChatGPT認証はAPIキーではなくユーザーのサブスクリプション状態に依存する。認証失効、利用上限、モデル提供状況の変更時には記事生成が失敗し得る。その場合に従量課金APIへ自動切替せず、Discordへ再認証または利用上限の確認が必要である旨を通知する。
