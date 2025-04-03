import os
import json
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

# Firecrawl APIキーを環境変数から取得
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")


def fetch_and_convert_to_markdown(
        url: str,
        cookie_file_path: str = "cookies.json"
):
    """
    指定した URL からクッキーを使用して HTML を取得し、
    サイトのタイトルとコンテンツを Markdown 文字列として返します。
    
    引数:
        url: データを取得するURL
        cookie_file_path: ブラウザでエクスポートした JSON 形式のクッキーファイル
    
    戻り値:
        tuple: (タイトル, 変換されたマークダウンコンテンツ)のタプル
    """
    try:
        # Firecrawlクライアントを初期化
        app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        
        # クッキーファイルを読み込む
        cookies = {}
        if os.path.exists(cookie_file_path):
            with open(cookie_file_path, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
            
            # クッキー文字列を作成
            cookie_str = ""
            for cookie in cookies_data:
                cookie_str += f"{cookie['name']}={cookie['value']}; "
            
            if cookie_str:
                cookies = {"Cookie": cookie_str.strip()}
        
        # Firecrawlのパラメータを設定
        params = {
            "formats": ["markdown", "html"],
            "pageOptions": {
                "headers": cookies
            }
        }
        
        # URLからコンテンツを取得
        response = app.scrape_url(url, params=params)
        
        # レスポンスからマークダウンとメタデータを取得
        if response and "data" in response:
            markdown_content = response["data"].get("markdown", "")
            metadata = response["data"].get("metadata", {})
            title = metadata.get("title", "")
            
            # タイトルが取得できない場合はURLをタイトルとして使用
            if not title:
                title = url
                
            return (title, markdown_content)
        else:
            print(f"Error: Unable to fetch content from {url}")
            return (None, None)
    except Exception as e:
        print(f"Error: {str(e)}")
        return (None, None)





if __name__ == "__main__":
    # 使い方例
    test_url = "https://howtomarketagame.com/2024/07/23/when-mostly-positive-games-dont-sell/"
    cookie_file = "cookies.json"  # クッキーファイル（JSON形式）
    
    # タイトルとマークダウンを取得
    title, markdown_content = fetch_and_convert_to_markdown(test_url, cookie_file)
    
    # 保存先フォルダの作成（存在しない場合は作成）
    download_folder = "downloaded"
    os.makedirs(download_folder, exist_ok=True)
    
    # ファイルに保存
    md_file_path = os.path.join(download_folder, "output.md")
    with open(md_file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    print(f"Title: {title}")
    print(f"Markdown file saved at: {md_file_path}")
