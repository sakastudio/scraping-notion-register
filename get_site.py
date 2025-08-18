import os
import json
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

# Firecrawl APIキーを環境変数から取得
load_dotenv()
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")


def fetch_and_convert_to_markdown(
        url: str ,
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
    # ★ 追加: APIキー未設定の明示的な検出
    if not FIRECRAWL_API_KEY:
        raise EnvironmentError("FIRECRAWL_API_KEY が設定されていません。環境変数を確認してください。")

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
    response = app.scrape_url(
        url,
        formats=["markdown", "html"],
        headers=cookies
    )

    # ★ 追加: 異常系は必ず例外を投げる（Noneを返さない）
    if not response:
        raise RuntimeError(f"Firecrawlが空のレスポンスを返しました: url={url}")

    if not isinstance(response, dict):
        raise TypeError(f"Firecrawlのレスポンス型が想定外です: type={type(response).__name__}, url={url}")

    # Firecrawl側のエラーフィールドを素直に拾う（ライブラリの仕様差異に広めに対応）
    if response.get("error"):
        raise RuntimeError(f"Firecrawlエラー: {response.get('error')} (url={url})")
    if response.get("status") == "error":
        msg = response.get("message") or response.get("error") or "unknown error"
        raise RuntimeError(f"Firecrawl status=error: {msg} (url={url})")

    if "markdown" not in response:
        raise ValueError(f"Firecrawlレスポンスに 'markdown' キーがありません。keys={list(response.keys())} (url={url})")

    # レスポンスからマークダウンとメタデータを取得
    markdown_content = response.get("markdown" , "")
    title = response.get("metadata", {}).get("title" , "")

    # タイトルが取得できない場合はURLをタイトルとして使用
    if not title:
        title = url

    return (title , markdown_content)


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
