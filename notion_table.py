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
        url: コンテンツのURL (Noneの場合はコンテンツから抽出を試みる)
        title: コンテンツのタイトル (Noneの場合はコンテンツから抽出)
    
    戻り値:
        dict: 作成されたNotionページの情報
    """
    if not NOTION_DATABASE_ID:
        raise ValueError("NOTION_DATABASE_IDが設定されていません。環境変数を確認してください。")
    
    # クライアント初期化
    notion = init_notion_client()

    # Notionページのプロパティを設定
    properties = {"タイトル": {
        "title": [
            {
                "text": {
                    "content": title
                }
            }
        ]
    } , "URL": {
        "url": url
    }}

    # ページ作成
    page_data = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "children": [
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
            },
        ]
    }
    
    # マークダウンの各段落をブロックとして追加
    # Notionの制限: リッチテキストは2000文字以下
    MAX_TEXT_LENGTH = 2000
    
    paragraphs = content.split('\n\n')
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
            
        # 長い段落を分割（2000文字以下のチャンクに）
        if len(paragraph) <= MAX_TEXT_LENGTH:
            # 2000文字以内なら1つのブロックとして追加
            page_data["children"].append({
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
                page_data["children"].append({
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
    
    # ページ作成APIを呼び出し
    try:
        response = notion.pages.create(**page_data)
        print(f"Notionページを作成しました: {title}")
        return response
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
