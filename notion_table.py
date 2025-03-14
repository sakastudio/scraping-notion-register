import os
import re
import json
from datetime import datetime
from urllib.parse import urlparse
from notion_client import Client

# Notion API設定
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DATABASE_ID = "bb656c8f12024b45afae5bb2ad03578d"


def init_notion_client():
    """Notion APIクライアントを初期化"""
    if not NOTION_TOKEN:
        raise ValueError("NOTION_TOKENが設定されていません。環境変数を確認してください。")
    
    return Client(auth=NOTION_TOKEN)


def register_notion_table(content: str, url: str, title: str):
    """
    マークダウンコンテンツをNotionのテーブルに登録する
    
    引数:
        content: マークダウンコンテンツ
        url: コンテンツのURL
        title: コンテンツのタイトル
    
    戻り値:
        dict: 作成されたNotionページの情報
    """
    if not NOTION_DATABASE_ID:
        raise ValueError("NOTION_DATABASE_IDが設定されていません。環境変数を確認してください。")
    
    # クライアント初期化
    notion = init_notion_client()

    # まずページ基本情報を作成する
    try:
        # ページプロパティのみでページを作成
        new_page = notion.pages.create(
            **{
                "parent": {
                    "type": "database_id",
                    "database_id": NOTION_DATABASE_ID
                },
                "properties": {
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
        
        # マークダウンの各段落をブロックとして追加
        # Notionの制限: リッチテキストは2000文字以下
        MAX_TEXT_LENGTH = 2000
        MAX_BLOCKS_PER_REQUEST = 90  # 1リクエストあたりの最大ブロック数
        
        # 段落を分割
        paragraphs = content.split('\n\n')
        blocks = []
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # 長い段落を分割（2000文字以下のチャンクに）
            if len(paragraph) <= MAX_TEXT_LENGTH:
                # 2000文字以内なら1つのブロックとして追加
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": paragraph
                                }
                            }
                        ]
                    }
                })
            else:
                # 長い段落は複数のブロックに分割
                for i in range(0, len(paragraph), MAX_TEXT_LENGTH):
                    chunk = paragraph[i:i+MAX_TEXT_LENGTH]
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": chunk
                                    }
                                }
                            ]
                        }
                    })
        
        # ブロックを適切なサイズのバッチに分割して追加
        for i in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
            batch = blocks[i:i+MAX_BLOCKS_PER_REQUEST]
            notion.blocks.children.append(
                block_id=page_id,
                children=batch
            )
            print(f"ブロックバッチを追加しました: {i//MAX_BLOCKS_PER_REQUEST + 1}/{(len(blocks)-1)//MAX_BLOCKS_PER_REQUEST + 1}")
        
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
    else:
        # テスト登録
        test_url = "https://newsletter.gamediscover.co/p/steams-top-grossing-games-of-2024"
        register_notion_table(content, url=test_url, title="テスト記事")
