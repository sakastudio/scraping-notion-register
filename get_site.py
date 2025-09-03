import os
import json
from dotenv import load_dotenv
from firecrawl import Firecrawl

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

    # 変更: Firecrawlクライアントを初期化（FirecrawlApp -> Firecrawl）
    app = Firecrawl(api_key=FIRECRAWL_API_KEY)

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

    # 変更: URLからコンテンツを取得（scrape_url -> scrape）
    response = app.scrape(
        url,
        formats=["markdown", "html"],
        headers=cookies  # v2 APIは headers をサポート
    )

    # --- ここから型差異を吸収する共通化処理（最小追加） ---
    def _to_dict(obj):
        """firecrawlの型付きレスポンス(ScrapeResponse等)やPydanticをdictに正規化"""
        if isinstance(obj, dict):
            return obj
        # Pydantic v2
        if hasattr(obj, "model_dump"):
            try:
                return obj.model_dump()
            except Exception:
                pass
        # Pydantic v1
        if hasattr(obj, "dict"):
            try:
                return obj.dict()
            except Exception:
                pass
        # dataclass/任意オブジェクトの __dict__
        if hasattr(obj, "__dict__"):
            try:
                return dict(obj.__dict__)
            except Exception:
                pass
        return None

    resp_dict = _to_dict(response)
    if not resp_dict:
        # ここでこけている（ScrapeResponse 等）ケースを明示
        raise TypeError(f"Firecrawlのレスポンス型が想定外です: type={type(response).__name__}, url={url}")

    # RESTの生レスポンスに近い形（success/data）にも、SDKが直接（markdown/metadata）にも対応
    container = resp_dict.get("data", resp_dict)

    # バッチ/クロール由来で list の可能性に保険（scrapeで来たら通常は単一）
    if isinstance(container, list):
        if len(container) == 1:
            container = container[0]
        else:
            raise ValueError(f"複数項目のレスポンスを受け取りました（想定外）: count={len(container)} url={url}")

    # Firecrawl 側エラーフィールドの拾い上げ
    if isinstance(container, dict) and container.get("error"):
        raise RuntimeError(f"Firecrawlエラー: {container.get('error')} (url={url})")

    # --- ここまで共通化処理 ---

    # レスポンスからマークダウンとメタデータを取得
    if not isinstance(container, dict):
        raise TypeError(f"レスポンス本体の型が想定外です: type={type(container).__name__}, url={url}")

    if "markdown" not in container:
        raise ValueError(f"'markdown' キーが見つかりません。keys={list(container.keys())} url={url}")

    markdown_content = container.get("markdown", "")

    # メタデータからタイトルを確実に取得
    metadata = container.get("metadata")
    title = ""

    if metadata and isinstance(metadata, dict):
        # 複数のタイトルフィールドを優先順位付きで確認
        title_candidates = [
            metadata.get("title"),
            metadata.get("ogTitle"),
            metadata.get("twitterTitle"),
            metadata.get("pageTitle"),
            metadata.get("dcTitle")
        ]

        # 最初の有効なタイトルを選択（空文字列でないもの）
        for candidate in title_candidates:
            if candidate and isinstance(candidate, str) and candidate.strip():
                title = candidate.strip()
                break

    # タイトルが取得できなかった場合はURLをフォールバックとして使用
    if not title:
        title = url

    return (title, markdown_content)


if __name__ == "__main__":
    # 使い方例
    test_url = "https://newsletter.gamediscover.co/p/schedule-is-solo-smash-hit-and-the"
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
