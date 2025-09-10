import os
import re  # 追加
from typing import List, Optional
from notion_client import Client

# タグ予測機能のインポート
from tag_predictor import load_tags_from_file, predict_tags

# Notion API設定
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = "bb656c8f12024b45afae5bb2ad03578d"


def init_notion_client():
    """Notion APIクライアントを初期化"""
    if not NOTION_TOKEN:
        raise ValueError("NOTION_TOKENが設定されていません。環境変数を確認してください。")
    
    return Client(auth=NOTION_TOKEN)


def register_notion_table(content: str, url: str, title: str, tags: Optional[List[str]] = None):
    """
    マークダウンコンテンツをNotionのテーブルに登録する
    
    引数:
        content: マークダウンコンテンツ
        url: コンテンツのURL
        title: コンテンツのタイトル
        tags: タグのリスト（指定しない場合はコンテンツから自動予測）
    
    戻り値:
        dict: 作成されたNotionページの情報
    """
    if not NOTION_DATABASE_ID:
        raise ValueError("NOTION_DATABASE_IDが設定されていません。環境変数を確認してください。")
    
    # クライアント初期化
    notion = init_notion_client()
    
    # タグが指定されていない場合は自動予測
    if tags is None:
        # 利用可能なタグをファイルから読み込み
        available_tags = load_tags_from_file()
        
        if available_tags:
            # コンテンツからタグを予測
            tags = predict_tags(content, title, available_tags)
            print(f"予測されたタグ: {tags}")
        else:
            tags = []
            print("タグのリストが読み込めなかったため、タグなしで登録します。")

    # まずページ基本情報を作成する
    try:
        # プロパティの設定
        properties = {
            "タイトル": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            },
            "URL": {
                "url": url
            }
        }
        
        # タグがある場合は追加
        if tags:
            properties["タグ"] = {
                "multi_select": [{"name": tag} for tag in tags]
            }
        
        # ページプロパティのみでページを作成
        new_page = notion.pages.create(
            **{
                "parent": {
                    "type": "database_id",
                    "database_id": NOTION_DATABASE_ID
                },
                "properties": properties
            }
        )
        
        page_id = new_page["id"]
        print(f"Notionページを作成しました: {title}")
        
        # 次にコンテンツをブロックとして追加
        # 先頭に導入文を追加
        notion.blocks.children.append(
            block_id=page_id,
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "以下、抽出したコンテンツ："
                                }
                            }
                        ]
                    }
                },
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                }
            ]
        )

        # Notionの制限: リッチテキストは2000文字以下
        MAX_TEXT_LENGTH = 1990
        MAX_BLOCKS_PER_REQUEST = 90  # 1リクエストあたりの最大ブロック数

        # ---- ブロック生成ヘルパー ----
        def _text_rich(text: str):
            return [{"type": "text", "text": {"content": text}}]

        def _paragraph_block(text: str):
            return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _text_rich(text)}}

        def _heading_block(level: int, text: str):
            level = max(1, min(level, 3))
            block_type = f"heading_{level}"
            return {
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": _text_rich(text), "is_toggleable": False},
            }

        def _bulleted_item_block(text: str):
            return {"object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _text_rich(text)}}

        def _numbered_item_block(text: str):
            return {"object": "block", "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": _text_rich(text)}}

        def _code_block(text: str, lang_hint: str):
            lang = (lang_hint or "").strip().lower()
            # ごく簡単な言語名の正規化
            mapping = {
                "sh": "shell",
                "bash": "shell",
                "zsh": "shell",
                "js": "javascript",
                "ts": "typescript",
                "py": "python",
                "c++": "cpp",
                "c#": "csharp",
                "objective-c": "objective-c",
                "text": "plain text",
                "txt": "plain text",
                "md": "markdown",
                "yml": "yaml",
            }
            lang = mapping.get(lang, lang if lang else "plain text")
            return {"object": "block", "type": "code", "code": {"rich_text": _text_rich(text), "language": lang}}

        def _add_long_text_as_blocks(text: str, make_block):
            """MAX_TEXT_LENGTHごとに分割してブロックを追加する（段落/コードなど共通）"""
            if not text:
                return []
            if len(text) <= MAX_TEXT_LENGTH:
                return [make_block(text)]
            out = []
            for i in range(0, len(text), MAX_TEXT_LENGTH):
                out.append(make_block(text[i:i + MAX_TEXT_LENGTH]))
            return out

        blocks: List[dict] = []

        # ---- 簡易Markdownパーサ ----
        lines = content.splitlines()
        in_code = False
        code_lang = ""
        code_buf: List[str] = []

        para_buf: List[str] = []
        in_list: Optional[str] = None  # None / "bulleted" / "numbered"

        def flush_paragraph():
            nonlocal para_buf
            text = "\n".join(para_buf).strip()
            para_buf = []
            if not text:
                return
            blocks.extend(_add_long_text_as_blocks(text, _paragraph_block))

        def flush_list():
            nonlocal in_list
            in_list = None  # 実ブロックは項目追加時に都度pushしているので状態だけ戻す

        def flush_code():
            nonlocal code_buf, code_lang
            code_text = "\n".join(code_buf)
            code_buf = []
            if code_text == "":
                return
            # コードも文字数上限に合わせて分割
            blocks.extend(_add_long_text_as_blocks(code_text, lambda t: _code_block(t, code_lang)))

        heading_re = re.compile(r"^(#{1,3})\s+(.*)$")
        bullet_re = re.compile(r"^[-*+]\s+(.*)$")
        numbered_re = re.compile(r"^\d+\.\s+(.*)$")

        for raw in lines + [""]:  # 最後にフラッシュ用の空行を追加
            line = raw.rstrip("\n")

            # コードフェンス開始/終了
            if line.strip().startswith("```"):
                fence = line.strip()
                if not in_code:
                    # 開始：先に現在の段落/リストをフラッシュ
                    flush_paragraph()
                    flush_list()
                    in_code = True
                    code_lang = fence[3:].strip()  # ```lang
                    code_buf = []
                else:
                    # 終了
                    in_code = False
                    flush_code()
                    code_lang = ""
                continue

            if in_code:
                code_buf.append(line)
                continue

            # 空行はセクション区切り
            if line.strip() == "":
                # 段落があればフラッシュ、リストはここで終わり
                flush_paragraph()
                flush_list()
                continue

            # 見出し
            m_h = heading_re.match(line.strip())
            if m_h:
                flush_paragraph()
                flush_list()
                level = len(m_h.group(1))
                heading_text = m_h.group(2).strip()
                if heading_text:
                    if len(heading_text) <= MAX_TEXT_LENGTH:
                        blocks.append(_heading_block(level, heading_text))
                    else:
                        # 先頭は見出し、残りは段落として分割
                        blocks.append(_heading_block(level, heading_text[:MAX_TEXT_LENGTH]))
                        rest = heading_text[MAX_TEXT_LENGTH:]
                        blocks.extend(_add_long_text_as_blocks(rest, _paragraph_block))
                continue

            # 箇条書き（・番号付き）
            m_b = bullet_re.match(line)
            m_n = numbered_re.match(line)
            if m_b:
                flush_paragraph()
                in_list = "bulleted"
                item_text = m_b.group(1).strip()
                # 長すぎる箇条書きは複数の箇条書きに分割（Notionの制限対応）
                blocks.extend(_add_long_text_as_blocks(item_text, _bulleted_item_block))
                continue
            if m_n:
                flush_paragraph()
                in_list = "numbered"
                item_text = m_n.group(1).strip()
                blocks.extend(_add_long_text_as_blocks(item_text, _numbered_item_block))
                continue

            # それ以外は通常段落の一部としてバッファ
            para_buf.append(line)

        # 念のため最後の残りをフラッシュ
        if in_code:
            flush_code()
        flush_paragraph()
        flush_list()

        # ブロックを適切なサイズのバッチに分割して追加
        for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
            batch = blocks[i:i + MAX_BLOCKS_PER_REQUEST]
            notion.blocks.children.append(
                block_id=page_id,
                children=batch
            )
            print(
                f"ブロックバッチを追加しました: {i // MAX_BLOCKS_PER_REQUEST + 1}/{(len(blocks) - 1) // MAX_BLOCKS_PER_REQUEST + 1}")

        return new_page
    except Exception as e:
        print(f"Notionページの作成に失敗しました: {e}")
        raise


if __name__ == "__main__":
    # テスト用
    with open("downloaded/output.md", "r", encoding="utf-8") as f:
        content = f.read()
    
    # 環境変数設定の確認
    if not NOTION_TOKEN:
        print("環境変数が設定されていません。以下の環境変数を設定してください:")
        print("NOTION_TOKEN - NotionのAPIトークン")
        print("OPENAI_API_KEY - OpenAI APIキー（タグ予測用）")
    else:
        # テスト登録（タグ自動予測）
        test_url = "https://newsletter.gamediscover.co/p/steams-top-grossing-games-of-2024"
        register_notion_table(content, url=test_url, title="テスト記事")
        
        # 手動でタグを指定する例
        # manual_tags = ["ゲーム", "ビジネス", "Steam"]
        # register_notion_table(content, url=test_url, title="テスト記事（手動タグ）", tags=manual_tags)
