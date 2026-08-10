import os
import json
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlparse, urlunsplit

import requests
import urllib3
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from firecrawl import Firecrawl
from markdownify import markdownify as md

# Firecrawl APIキーを環境変数から取得
load_dotenv()
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")


MAX_DIRECT_HTML_BYTES = 5 * 1024 * 1024
DIRECT_REQUEST_TIMEOUT_SECONDS = 20
MAX_DIRECT_REDIRECTS = 5


def _resolve_public_ip(url: str, timeout_seconds: float = 5) -> str:
    """公開HTTP(S) URLを検証し、接続に固定する公開IPを返す。"""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"公開HTTP(S) URLではありません: {url}")

    resolution = {}

    def resolve():
        try:
            resolution["addresses"] = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        except Exception as error:
            resolution["error"] = error

    resolver = threading.Thread(target=resolve, daemon=True)
    resolver.start()
    resolver.join(max(0.001, timeout_seconds))
    if resolver.is_alive():
        raise TimeoutError(f"公開HTTP(S)ホストの名前解決がタイムアウトしました: {url}")
    if "error" in resolution:
        raise ValueError(f"公開HTTP(S)ホストを解決できません: {url}") from resolution["error"]
    addresses = resolution.get("addresses", [])

    public_ips = [item[4][0] for item in addresses if ipaddress.ip_address(item[4][0]).is_global]
    if not addresses or len(public_ips) != len(addresses):
        raise ValueError(f"公開HTTP(S)ホストではありません: {url}")
    return str(public_ips[0])


def convert_html_to_markdown(html: str | bytes, url: str):
    """HTMLからタイトルと本文Markdownを抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_title_content = str(og_title.get("content") or "").strip() if isinstance(og_title, Tag) else ""
    title = (
        og_title_content
        or (title_tag.get_text(" ", strip=True) if title_tag else "")
        or url
    )

    for element in soup.select("script, style, noscript, svg, nav, footer"):
        element.decompose()
    content_root = soup.find("main") or soup.find("article") or soup.body or soup
    markdown_content = md(str(content_root), heading_style="ATX", bullets="-").strip()
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
    if not markdown_content:
        raise ValueError(f"直接取得したHTMLに本文がありません: {url}")
    return title, markdown_content


def fetch_public_html_to_markdown(url: str):
    """公開HTTP(S)ページへ検証済みIPを固定して直接取得する。"""
    current_url = url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; scraping-notion-register/1.0)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    }
    deadline = time.monotonic() + DIRECT_REQUEST_TIMEOUT_SECONDS

    for redirect_count in range(MAX_DIRECT_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"直接取得が{DIRECT_REQUEST_TIMEOUT_SECONDS}秒を超えました: {current_url}")
        parsed = urlparse(current_url)
        target_ip = _resolve_public_ip(current_url, timeout_seconds=min(5, remaining))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"直接取得が{DIRECT_REQUEST_TIMEOUT_SECONDS}秒を超えました: {current_url}")
        hostname = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        host_header = hostname if port in {80, 443} else f"{hostname}:{port}"
        request_headers = {**headers, "Host": host_header}
        request_path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        pool_kwargs = {
            "port": port,
            "timeout": urllib3.Timeout(connect=min(5, remaining), read=min(10, remaining)),
            "retries": False,
        }
        if parsed.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                target_ip,
                assert_hostname=hostname,
                server_hostname=hostname,
                **pool_kwargs,
            )
        else:
            pool = urllib3.HTTPConnectionPool(target_ip, **pool_kwargs)

        response = None
        try:
            response = pool.request(
                "GET",
                request_path,
                headers=request_headers,
                redirect=False,
                preload_content=False,
            )
            if response.status in {301, 302, 303, 307, 308}:
                if redirect_count >= MAX_DIRECT_REDIRECTS:
                    raise ValueError(f"直接取得のリダイレクト回数が上限を超えました: {url}")
                location = response.headers.get("Location")
                if not location:
                    raise ValueError(f"直接取得のリダイレクト先がありません: {current_url}")
                current_url = urljoin(current_url, location)
                continue

            if response.status >= 400:
                raise RuntimeError(f"直接取得がHTTP {response.status}で失敗しました: {current_url}")
            content_type = response.headers.get("Content-Type", "").lower()
            media_type = content_type.split(";", 1)[0].strip()
            if media_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"直接取得先がHTMLではありません ({content_type}): {current_url}")

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError as error:
                    raise ValueError(f"直接取得先のContent-Lengthが不正です: {current_url}") from error
                if declared_length < 0 or declared_length > MAX_DIRECT_HTML_BYTES:
                    raise ValueError(f"直接取得するHTMLが大きすぎます: {current_url}")

            chunks = []
            total = 0
            for chunk in response.stream(amt=64 * 1024, decode_content=True):
                if time.monotonic() > deadline:
                    raise TimeoutError(f"直接取得が{DIRECT_REQUEST_TIMEOUT_SECONDS}秒を超えました: {current_url}")
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DIRECT_HTML_BYTES:
                    raise ValueError(f"直接取得するHTMLが大きすぎます: {current_url}")
                chunks.append(chunk)
            return convert_html_to_markdown(b"".join(chunks), current_url)
        finally:
            if response is not None:
                response.release_conn()
            pool.close()

    raise RuntimeError(f"直接取得に失敗しました: {url}")



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
    try:
        response = app.scrape(
            url,
            formats=["markdown", "html"],
            headers=cookies  # v2 APIは headers をサポート
        )
    except Exception as firecrawl_error:
        print(f"Firecrawl取得に失敗したため直接HTML取得へフォールバックします: {firecrawl_error}")
        try:
            return fetch_public_html_to_markdown(url)
        except Exception as direct_error:
            raise RuntimeError(
                f"Firecrawl取得失敗: {firecrawl_error}; 直接HTML取得失敗: {direct_error}"
            ) from direct_error

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
