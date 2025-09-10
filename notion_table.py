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

        # ---- ブロック生成ヘルパー（リンク対応） ----
        link_re = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

        def _split_text_to_rich(text: str, link_url: Optional[str] = None):
            """単一のテキストをMAX_TEXT_LENGTH以下のrich_text配列に分割"""
            if text == "":
                return []
            items = []
            for i in range(0, len(text), MAX_TEXT_LENGTH):
                chunk = text[i:i + MAX_TEXT_LENGTH]
                rt = {"type": "text", "text": {"content": chunk}}
                if link_url:
                    rt["text"]["link"] = {"url": link_url}
                items.append(rt)
            return items

        def _inline_to_rich(text: str):
            """
            段落等のインライン文字列に含まれる [label](url) を rich_text 配列へ変換。
            それ以外は通常テキストとして保持。
            """
            rich_parts = []
            pos = 0
            for m in link_re.finditer(text):
                start, end = m.span()
                label = m.group(1)
                url_ = m.group(2)
                # 直前のプレーンテキスト
                if start > pos:
                    rich_parts.extend(_split_text_to_rich(text[pos:start]))
                # リンク部分
                rich_parts.extend(_split_text_to_rich(label, link_url=url_))
                pos = end
            # 残り
            if pos < len(text):
                rich_parts.extend(_split_text_to_rich(text[pos:]))
            return rich_parts or [{"type": "text", "text": {"content": ""}}]

        def _paragraph_block_rich(rich_text: List[dict]):
            return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text}}

        def _heading_block(level: int, text: str):
            level = max(1, min(level, 3))
            block_type = f"heading_{level}"
            return {
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": _inline_to_rich(text), "is_toggleable": False},
            }

        def _bulleted_item_block_rich(rich_text: List[dict]):
            return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich_text}}

        def _numbered_item_block_rich(rich_text: List[dict]):
            return {"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": rich_text}}

        def _quote_block_rich(rich_text: List[dict]):
            return {"object": "block", "type": "quote", "quote": {"rich_text": rich_text}}

        def _todo_block_rich(rich_text: List[dict], checked: bool):
            return {"object": "block", "type": "to_do", "to_do": {"rich_text": rich_text, "checked": checked}}

        def _code_block(text: str, lang_hint: str):
            lang = (lang_hint or "").strip().lower()
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
            return {"object": "block", "type": "code",
                    "code": {"rich_text": _split_text_to_rich(text), "language": lang}}

        def _add_inline_as_blocks(text: str, make_block_rich):
            """
            インライン要素（リンク含む）をMAX_TEXT_LENGTHごとの塊で分割し、ブロック配列に。
            make_block_rich(rich_text) を用いて種類別のブロックを生成。
            """
            segs = _inline_to_rich(text)  # ここで各segmentはMAX_TEXT_LENGTH以下
            blocks_local = []
            cur: List[dict] = []
            cur_len = 0
            for seg in segs:
                seg_len = len(seg["text"]["content"])
                if cur_len + seg_len > MAX_TEXT_LENGTH and cur:
                    blocks_local.append(make_block_rich(cur))
                    cur = []
                    cur_len = 0
                cur.append(seg)
                cur_len += seg_len
            if cur:
                blocks_local.append(make_block_rich(cur))
            return blocks_local

        def _add_long_text_as_blocks(text: str, make_block_str):
            """プレーンテキスト（主にコード/見出しの分割用）をMAX_TEXT_LENGTHごとに分割"""
            if not text:
                return []
            if len(text) <= MAX_TEXT_LENGTH:
                return [make_block_str(text)]
            out = []
            for i in range(0, len(text), MAX_TEXT_LENGTH):
                out.append(make_block_str(text[i:i + MAX_TEXT_LENGTH]))
            return out

        blocks: List[dict] = []

        # ---- 簡易Markdownパーサ ----
        lines = content.splitlines()
        in_code = False
        code_lang = ""
        code_buf: List[str] = []

        para_buf: List[str] = []

        heading_re = re.compile(r"^(#{1,3})\s+(.*)$")
        bullet_re = re.compile(r"^[-*+]\s+(.*)$")
        numbered_re = re.compile(r"^\d+\.\s+(.*)$")
        todo_bullet_re = re.compile(r"^[-*+]\s+\[( |x|X)\]\s+(.*)$")
        todo_numbered_re = re.compile(r"^\d+\.\s+\[( |x|X)\]\s+(.*)$")
        quote_re = re.compile(r"^>\s?(.*)$")

        def flush_paragraph():
            nonlocal para_buf
            text = "\n".join(para_buf).strip()
            para_buf = []
            if not text:
                return
            blocks.extend(_add_inline_as_blocks(text, _paragraph_block_rich))

        def flush_code():
            nonlocal code_buf, code_lang
            code_text = "\n".join(code_buf)
            code_buf = []
            if code_text == "":
                return
            blocks.extend(_add_long_text_as_blocks(code_text, lambda t: _code_block(t, code_lang)))

        for raw in lines + [""]:  # 最後にフラッシュ用の空行を追加
            line = raw.rstrip("\n")

            # コードフェンス開始/終了
            if line.strip().startswith("```"):
                fence = line.strip()
                if not in_code:
                    # 開始：先に現在の段落をフラッシュ
                    flush_paragraph()
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

            # 空行はセクション区切り（段落フラッシュ）
            if line.strip() == "":
                flush_paragraph()
                continue

            # 見出し
            m_h = heading_re.match(line.strip())
            if m_h:
                flush_paragraph()
                level = len(m_h.group(1))
                heading_text = m_h.group(2).strip()
                if heading_text:
                    if len(heading_text) <= MAX_TEXT_LENGTH:
                        blocks.append(_heading_block(level, heading_text))
                    else:
                        blocks.append(_heading_block(level, heading_text[:MAX_TEXT_LENGTH]))
                        rest = heading_text[MAX_TEXT_LENGTH:]
                        blocks.extend(_add_inline_as_blocks(rest, _paragraph_block_rich))
                continue

            # 引用
            m_q = quote_re.match(line)
            if m_q:
                flush_paragraph()
                q_text = m_q.group(1).strip()
                blocks.extend(_add_inline_as_blocks(q_text, _quote_block_rich))
                continue

            # チェックボックス（to_do）
            m_tb = todo_bullet_re.match(line)
            m_tn = todo_numbered_re.match(line)
            if m_tb or m_tn:
                flush_paragraph()
                checked = (m_tb.group(1) if m_tb else m_tn.group(1)).lower() == "x"
                t_text = (m_tb.group(2) if m_tb else m_tn.group(2)).strip()
                # 文字数オーバー時は複数のto_doに分割（checkedは維持）
                seg_blocks = _add_inline_as_blocks(t_text, lambda rich: _todo_block_rich(rich, checked))
                blocks.extend(seg_blocks)
                continue

            # 箇条書き（通常）
            m_b = bullet_re.match(line)
            if m_b:
                flush_paragraph()
                item_text = m_b.group(1).strip()
                blocks.extend(_add_inline_as_blocks(item_text, _bulleted_item_block_rich))
                continue

            # 番号付き
            m_n = numbered_re.match(line)
            if m_n:
                flush_paragraph()
                item_text = m_n.group(1).strip()
                blocks.extend(_add_inline_as_blocks(item_text, _numbered_item_block_rich))
                continue

            # それ以外は通常段落の一部としてバッファ
            para_buf.append(line)

        # 念のため最後の残りをフラッシュ
        if in_code:
            flush_code()
        flush_paragraph()

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
