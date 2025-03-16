import os
import time

# 既存の機能をインポート
from get_site import fetch_and_convert_to_markdown
from notion_table import register_notion_table
from title_translator import is_non_japanese_title, translate_title

# 固定のファイル名
URL_LIST_FILE = 'url_list.txt'
# URLごとの処理間の待機時間（秒）- API制限対策
DELAY_BETWEEN_REQUESTS = 1.0

def process_url(url):
    """
    URLを処理してNotionテーブルに登録する
    """
    try:
        print(f"処理開始: {url}")
        print("サイトのコンテンツを取得しています...")
        
        # サイトのタイトルとコンテンツを取得
        title, content = fetch_and_convert_to_markdown(url)
        if not content:
            print(f"❌ コンテンツの取得に失敗しました: {url}")
            return False
        
        # タイトルの翻訳（英語など日本語以外の場合）
        original_title = title
        if is_non_japanese_title(title):
            print("タイトルを翻訳しています...")
            translated_title = translate_title(title)
            if translated_title:
                title = f"{translated_title} (原題: {original_title})"
        
        print("Notionテーブルに登録しています...")
        
        # Notionテーブルに登録 (タグは自動予測)
        page = register_notion_table(content, url=url, title=title, tags=None)
        
        # 完了メッセージ
        page_url = page.get("url", "不明")
        
        print(f"✅ 登録完了!")
        print(f"タイトル: {title}")
        print(f"元URL: {url}")
        print(f"Notion URL: {page_url}")
        print("-" * 50)
        
        return True
    
    except Exception as e:
        print(f"❌ 処理中にエラーが発生しました: {str(e)}")
        return False

# メイン処理
print("URLリストからNotionテーブルへの登録処理を開始します")

# URLの読み込み
try:
    with open(URL_LIST_FILE, 'r', encoding='utf-8') as f:
        # 空行やコメント行（#で始まる行）を除外
        urls = [line.strip() for line in f.readlines() 
               if line.strip() and not line.strip().startswith('#')]
except Exception as e:
    print(f"URLリストファイルの読み込みに失敗しました: {str(e)}")
    urls = []

if not urls:
    print(f"処理するURLが見つかりません: {URL_LIST_FILE}")
    exit(1)

print(f"URLリスト読み込み完了 - {len(urls)}件のURLを処理します\n")

# 結果カウンター
success_count = 0
failed_urls = []

# URLの処理
for idx, url in enumerate(urls):
    success = process_url(url)
    if success:
        success_count += 1
    else:
        failed_urls.append(url)
    
    # 進捗表示
    print(f"進捗: {idx + 1}/{len(urls)} - 完了率: {(idx + 1) / len(urls) * 100:.1f}%")
    
    # 次のURLを処理する前に少し待機（API制限対策）
    if idx < len(urls) - 1:
        time.sleep(DELAY_BETWEEN_REQUESTS)

# 結果のサマリーを表示
print("\n=== 処理結果サマリー ===")
print(f"処理したURL: {len(urls)}件")
print(f"成功: {success_count}件")
print(f"失敗: {len(urls) - success_count}件")

# 失敗したURLがあれば表示
if failed_urls:
    print("\n=== 失敗したURL ===")
    for url in failed_urls:
        print(f"{url}")

print("\n処理完了!")