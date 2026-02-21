import re
import requests
from typing import Tuple, Optional, Dict, List


# Playwright の遅延インポート（フォールバック時のみ使用）
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    print("警告: Playwrightがインストールされていません。fxtwitter APIのみを使用します。")


def _extract_post_id(url: str) -> str:
    """X/Twitter URLからポストIDを抽出"""
    match = re.search(r'/status/(\d+)', url)
    if not match:
        raise ValueError(f"ポストIDが見つかりません。ポストURLを指定してください: {url}")
    return match.group(1)


def _normalize_x_url(url: str) -> str:
    """X/Twitter URLを正規化（x.com形式に統一）"""
    return re.sub(r'https?://(www\.)?(twitter\.com|mobile\.twitter\.com)', 'https://x.com', url)


def _fetch_via_fxtwitter_api(url: str) -> Optional[Dict]:
    """
    fxtwitter APIから構造化データを取得（ブラウザ不要）

    戻り値:
        dict: ポストデータ or None（失敗時）
    """
    # URL変換: x.com/user/status/123 -> api.fxtwitter.com/user/status/123
    api_url = re.sub(
        r'https?://(www\.)?(twitter\.com|x\.com|mobile\.twitter\.com)',
        'https://api.fxtwitter.com',
        url
    )

    try:
        response = requests.get(api_url, timeout=15)
        if response.status_code != 200:
            print(f"fxtwitter API エラー: status={response.status_code}")
            return None

        data = response.json()
        tweet = data.get("tweet")
        if not tweet:
            print("fxtwitter API: tweetフィールドが見つかりません")
            return None

        # 画像URLの抽出
        images = []
        media = tweet.get("media")
        if media:
            photos = media.get("photos", [])
            for photo in photos:
                img_url = photo.get("url")
                if img_url:
                    images.append(img_url)

        return {
            "text": tweet.get("text", ""),
            "author_name": tweet.get("author", {}).get("name", ""),
            "author_handle": tweet.get("author", {}).get("screen_name", ""),
            "timestamp": tweet.get("created_at", ""),
            "images": images,
        }
    except requests.RequestException as e:
        print(f"fxtwitter API リクエストエラー: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"fxtwitter API パースエラー: {e}")
        return None


def _fetch_via_playwright(url: str) -> Optional[Dict]:
    """
    Playwrightで直接X/Twitterページをレンダリングして取得（フォールバック）

    戻り値:
        dict: ポストデータ or None（失敗時）
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("Playwrightが利用できません")
        return None

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
            # ツイートテキストの表示を待機
            page.wait_for_selector('[data-testid="tweetText"]', timeout=15000)

            # テキスト取得
            tweet_text_el = page.query_selector('[data-testid="tweetText"]')
            text = tweet_text_el.inner_text() if tweet_text_el else ""

            # 著者情報取得
            author_el = page.query_selector('[data-testid="User-Name"]')
            author_raw = author_el.inner_text() if author_el else ""
            # User-Nameには "DisplayName\n@handle" 形式が含まれる
            author_parts = author_raw.split("\n") if author_raw else []
            author_name = author_parts[0].strip() if len(author_parts) > 0 else ""
            author_handle = ""
            for part in author_parts:
                if part.strip().startswith("@"):
                    author_handle = part.strip().lstrip("@")
                    break

            # タイムスタンプ取得
            time_el = page.query_selector("time")
            timestamp = time_el.get_attribute("datetime") if time_el else ""

            # 画像URL取得
            images = []
            img_elements = page.query_selector_all('[data-testid="tweetPhoto"] img')
            for img in img_elements:
                src = img.get_attribute("src")
                if src and "pbs.twimg.com" in src:
                    # 高画質版に変換
                    src = re.sub(r'name=\w+', 'name=large', src)
                    images.append(src)

            return {
                "text": text,
                "author_name": author_name,
                "author_handle": author_handle,
                "timestamp": timestamp,
                "images": images,
            }
        except Exception as e:
            print(f"Playwright取得エラー: {e}")
            return None
        finally:
            browser.close()


def _format_as_markdown(data: Dict, original_url: str) -> Tuple[str, str]:
    """取得したポストデータをマークダウン形式に変換"""
    author_name = data.get("author_name", "不明")
    author_handle = data.get("author_handle", "")
    text = data.get("text", "")
    timestamp = data.get("timestamp", "")
    images = data.get("images", [])

    # タイトル生成
    if len(text) > 50:
        title = f"@{author_handle}: {text[:50]}..."
    else:
        title = f"@{author_handle}: {text}" if text else f"@{author_handle} のポスト"

    # マークダウンコンテンツ生成
    lines = []
    lines.append(f"## {author_name} (@{author_handle})")
    if timestamp:
        lines.append(f"**投稿日時**: {timestamp}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(text)
    lines.append("")

    # 画像をマークダウン画像構文で追加
    if images:
        lines.append("### 添付画像")
        lines.append("")
        for i, img_url in enumerate(images, 1):
            lines.append(f"![画像{i}]({img_url})")
            lines.append("")

    return (title, "\n".join(lines))


def fetch_x_post(url: str) -> Tuple[str, str]:
    """
    X/Twitterのポストを取得し、マークダウンとして返す

    Tier1: fxtwitter API（高速・軽量）
    Tier2: Playwright（フォールバック）

    引数:
        url: X/TwitterのポストURL

    戻り値:
        tuple: (タイトル, マークダウンコンテンツ)
    """
    # ポストIDの存在確認
    _extract_post_id(url)

    # Tier 1: fxtwitter API
    print(f"fxtwitter APIで取得を試みます: {url}")
    data = _fetch_via_fxtwitter_api(url)

    # Tier 2: Playwright フォールバック
    if data is None:
        print("fxtwitter APIでの取得に失敗。Playwrightで再試行します...")
        data = _fetch_via_playwright(url)

    if data is None:
        raise RuntimeError(
            f"X/Twitterポストの取得に失敗しました。"
            f"fxtwitter APIとPlaywrightの両方で取得できませんでした: {url}"
        )

    return _format_as_markdown(data, url)


if __name__ == "__main__":
    test_urls = [
        "https://x.com/elikinosita/status/1892818905975779378",
    ]

    for test_url in test_urls:
        print(f"\nテスト URL: {test_url}")
        print("-" * 50)
        try:
            title, content = fetch_x_post(test_url)
            print(f"タイトル: {title}")
            print(f"コンテンツ長: {len(content)}文字")
            print()
            print(content)
        except Exception as e:
            print(f"エラー: {e}")
