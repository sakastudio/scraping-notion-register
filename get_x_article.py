import re
import time
from typing import Tuple, Optional, List
from urllib.parse import urlparse


# Playwright の遅延インポート（利用不可でもインポートエラーにならない）
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    print("警告: Playwrightがインストールされていません。X記事の取得にはPlaywrightが必要です。")


# X記事URLの正規表現パターン
X_ARTICLE_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/article/(\d+)'
)


def is_x_article_url(url: str) -> bool:
    """X/Twitterの記事（Article）URLかどうかを判定"""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        x_domains = ['x.com', 'twitter.com', 'www.x.com', 'www.twitter.com', 'mobile.twitter.com']
        if hostname not in x_domains:
            return False
        return bool(re.match(r'^/\w+/article/\d+', parsed.path))
    except Exception:
        return False


def _normalize_x_url(url: str) -> str:
    """X/Twitter URLを正規化（x.com形式に統一）"""
    return re.sub(
        r'https?://(www\.)?(twitter\.com|mobile\.twitter\.com)',
        'https://x.com', url
    )


def _convert_article_dom_to_markdown(page) -> Tuple[str, str, str, str]:
    """
    X記事のDOMを解析してMarkdownに変換

    戻り値:
        tuple: (タイトル, 著者情報, Markdown本文, タイムスタンプ)
    """
    # タイトルの取得
    title_el = page.query_selector('[data-testid="twitter-article-title"]')
    if not title_el:
        # フォールバック: 最初のlongform-header-oneを探す
        title_el = page.query_selector('[class*="longform-header-one"]')
    title = title_el.inner_text().strip() if title_el else ""

    # 著者の取得
    author_el = page.query_selector('[data-testid="User-Name"]')
    author_raw = author_el.inner_text() if author_el else ""
    author_parts = author_raw.split("\n") if author_raw else []
    author_name = author_parts[0].strip() if author_parts else ""
    author_handle = ""
    for part in author_parts:
        if part.strip().startswith("@"):
            author_handle = part.strip().lstrip("@")
            break

    # タイムスタンプの取得
    time_el = page.query_selector("time")
    timestamp = time_el.get_attribute("datetime") if time_el else ""

    # コンテンツブロックの取得と変換
    content_blocks = page.query_selector_all(
        '[class*="longform-header-one"], '
        '[class*="longform-header-two"], '
        '[class*="longform-unstyled"], '
        '[class*="longform-unordered-list-item"], '
        '[class*="longform-ordered-list-item"], '
        '[class*="longform-blockquote"]'
    )

    lines = []
    ordered_counter = 0
    skip_title = True  # 最初のheader-oneはタイトルとして使用済みなのでスキップ

    for block in content_blocks:
        class_attr = block.get_attribute("class") or ""
        text = block.inner_text().strip()

        # 画像ブロックの処理（テキストが空の場合）
        if not text:
            img = block.query_selector("img")
            if img:
                src = img.get_attribute("src") or ""
                alt = img.get_attribute("alt") or "画像"
                if src:
                    # 画像URLの最適化
                    if "pbs.twimg.com" in src:
                        src = re.sub(r'name=\w+', 'name=large', src)
                    lines.append(f"![{alt}]({src})")
                    lines.append("")
            continue

        if "longform-header-one" in class_attr:
            # 最初のheader-oneがタイトルと同じならスキップ
            if skip_title and title and text == title:
                skip_title = False
                continue
            skip_title = False
            ordered_counter = 0
            lines.append(f"# {text}")
            lines.append("")
        elif "longform-header-two" in class_attr:
            skip_title = False
            ordered_counter = 0
            lines.append(f"## {text}")
            lines.append("")
        elif "longform-unordered-list-item" in class_attr:
            skip_title = False
            ordered_counter = 0
            lines.append(f"- {text}")
        elif "longform-ordered-list-item" in class_attr:
            skip_title = False
            ordered_counter += 1
            lines.append(f"{ordered_counter}. {text}")
        elif "longform-blockquote" in class_attr:
            skip_title = False
            ordered_counter = 0
            lines.append(f"> {text}")
            lines.append("")
        else:
            # longform-unstyled（通常の段落）
            skip_title = False
            ordered_counter = 0
            lines.append(text)
            lines.append("")

    # ブロック間の独立した画像も取得
    article_images = page.query_selector_all('article img, [data-testid="tweetPhoto"] img')
    seen_srcs = set()
    for img in article_images:
        src = img.get_attribute("src") or ""
        if src and "pbs.twimg.com" in src and src not in seen_srcs:
            src = re.sub(r'name=\w+', 'name=large', src)
            # Markdown本文に既に含まれていなければ追加
            if src not in "\n".join(lines):
                seen_srcs.add(src)
                alt = img.get_attribute("alt") or "画像"
                lines.append(f"![{alt}]({src})")
                lines.append("")

    author_info = f"{author_name} (@{author_handle})" if author_handle else author_name
    markdown_body = "\n".join(lines)

    return (title, author_info, markdown_body, timestamp)


def fetch_x_article(url: str) -> Tuple[str, str]:
    """
    Xの記事（Article）を取得し、マークダウンとして返す

    引数:
        url: X記事のURL（例: https://x.com/username/article/12345）

    戻り値:
        tuple: (タイトル, マークダウンコンテンツ)
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("X記事の取得にはPlaywrightが必要です。pip install playwright && playwright install chromium を実行してください。")

    normalized_url = _normalize_x_url(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
        )
        page = context.new_page()

        try:
            page.goto(normalized_url, wait_until="networkidle", timeout=30000)

            # 記事コンテンツの読み込みを待機
            try:
                page.wait_for_selector(
                    '[class*="longform-unstyled"], [class*="longform-header"]',
                    timeout=15000
                )
            except Exception:
                raise RuntimeError(
                    f"記事コンテンツが見つかりません。ログインが必要な可能性があります: {url}"
                )

            # 遅延読み込みに対応するためページ全体をスクロール
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

            title, author_info, markdown_body, timestamp = _convert_article_dom_to_markdown(page)

            if not title:
                title = f"X Article by {author_info}" if author_info else "X Article"

            # タイトルから改行を除去
            title = re.sub(r'[\r\n]+', ' ', title).strip()

            # メタデータヘッダーを含む完全なMarkdownを構築
            full_lines = []
            if author_info:
                full_lines.append(f"**著者**: {author_info}")
            if timestamp:
                full_lines.append(f"**公開日時**: {timestamp}")
            full_lines.append(f"**URL**: {normalized_url}")
            full_lines.append("")
            full_lines.append("---")
            full_lines.append("")
            full_lines.append(markdown_body)

            content = "\n".join(full_lines)
            return (title, content)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"X記事の取得に失敗しました: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    test_url = "https://x.com/example/article/12345"

    print(f"テスト URL: {test_url}")
    print("-" * 50)
    try:
        title, content = fetch_x_article(test_url)
        print(f"タイトル: {title}")
        print(f"コンテンツ長: {len(content)}文字")
        print()
        print(content)
    except Exception as e:
        print(f"エラー: {e}")
