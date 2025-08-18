import os
import json
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

# Firecrawl APIキーを環境変数から取得
load_dotenv()
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")


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
    # Firecrawlクライアントを初期化
    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

    # クッキーファイルを読み込む
    cookies = {}
    if os.path.exists(cookie_file_path):
        with open(cookie_file_path , 'r' , encoding='utf-8') as f:
            cookies_data = json.load(f)

        # クッキー文字列を作成
        cookie_str = ""
        for cookie in cookies_data:
            cookie_str += f"{cookie['name']}={cookie['value']}; "

        if cookie_str:
            cookies = {"Cookie": cookie_str.strip()}

    # URLからコンテンツを取得（v1では params を使わず、引数で直接渡す）
    try:
        response = app.scrape_url(
            url,
            formats=["markdown", "html"],
            headers=cookies
        )
    except Exception as e:
        # Firecrawl 呼び出しで例外が出た場合でも常にタプルを返す
        print(f"Firecrawl scrape エラー: {e}")
        return (url or "", "")

    # レスポンスからマークダウンとメタデータを取得
    if response and isinstance(response, dict) and "markdown" in response:
        markdown_content = response.get("markdown", "")
        metadata = response.get("metadata", {}) or {}
        title = metadata.get("title", "")

        # タイトルが取得できない場合はURLをタイトルとして使用
        if not title:
            title = url

        return (title, markdown_content)

    # 期待するフィールドが無い場合も常にタプルを返す
    return (url or "", "")


if __name__ == "__main__":
    # 使い方例
    test_url = "https://newsletter.gamediscover.co/p/schedule-is-solo-smash-hit-and-the"
    cookie_file = "cookies.json"  # クッキーファイル（JSON形式）

    # タイトルとマークダウンを取得
    title , markdown_content = fetch_and_convert_to_markdown(test_url , cookie_file)

    # 保存先フォルダの作成（存在しない場合は作成）
    download_folder = "downloaded"
    os.makedirs(download_folder , exist_ok=True)

    # ファイルに保存
    md_file_path = os.path.join(download_folder , "output.md")
    with open(md_file_path , "w" , encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"Title: {title}")
    print(f"Markdown file saved at: {md_file_path}")
