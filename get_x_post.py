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

# X/Twitter URLの正規表現パターン
X_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com|mobile\.twitter\.com)/\w+/status/(\d+)'
)

# 再帰の最大深度（無限ループ防止）
MAX_RECURSION_DEPTH = 10


def _extract_post_id(url: str) -> str:
    """X/Twitter URLからポストIDを抽出"""
    match = re.search(r'/status/(\d+)', url)
    if not match:
        raise ValueError(f"ポストIDが見つかりません。ポストURLを指定してください: {url}")
    return match.group(1)


def _normalize_x_url(url: str) -> str:
    """X/Twitter URLを正規化（x.com形式に統一）"""
    return re.sub(r'https?://(www\.)?(twitter\.com|mobile\.twitter\.com)', 'https://x.com', url)


def _extract_images_from_tweet(tweet: Dict) -> List[str]:
    """tweetオブジェクトから画像URLを抽出"""
    images = []
    media = tweet.get("media")
    if media:
        photos = media.get("photos", [])
        for photo in photos:
            img_url = photo.get("url")
            if img_url:
                images.append(img_url)
    return images


def _parse_tweet_data(tweet: Dict) -> Dict:
    """fxtwitter APIのtweetオブジェクトを共通データ形式に変換"""
    return {
        "text": tweet.get("text", ""),
        "author_name": tweet.get("author", {}).get("name", ""),
        "author_handle": tweet.get("author", {}).get("screen_name", ""),
        "timestamp": tweet.get("created_at", ""),
        "url": tweet.get("url", ""),
        "images": _extract_images_from_tweet(tweet),
    }


def _extract_x_urls_from_text(text: str) -> List[str]:
    """テキストからX/Twitter URLを抽出"""
    return X_URL_PATTERN.findall(text)


def _fetch_tweet_raw(url: str) -> Optional[Dict]:
    """
    fxtwitter APIから生のtweetオブジェクトを取得

    戻り値:
        dict: fxtwitter APIのtweetオブジェクト or None
    """
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
            print(f"fxtwitter API: tweetフィールドが見つかりません: {url}")
            return None

        return tweet
    except requests.RequestException as e:
        print(f"fxtwitter API リクエストエラー: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"fxtwitter API パースエラー: {e}")
        return None


def _collect_all_tweets_from_api(url: str, visited: Optional[set] = None, depth: int = 0) -> List[Dict]:
    """
    fxtwitter APIを使って、引用ツイートとテキスト中のX URLを再帰的にすべて取得

    引数:
        url: 起点となるポストURL
        visited: 処理済みポストIDのセット（循環防止）
        depth: 現在の再帰深度

    戻り値:
        list: 取得した全ポストデータのリスト（先頭が元ツイート）
    """
    if visited is None:
        visited = set()

    if depth > MAX_RECURSION_DEPTH:
        print(f"再帰深度の上限に達しました: {url}")
        return []

    post_id = _extract_post_id(url)
    if post_id in visited:
        return []
    visited.add(post_id)

    tweet_raw = _fetch_tweet_raw(url)
    if tweet_raw is None:
        return []

    result = [_parse_tweet_data(tweet_raw)]

    # 1. quote フィールドの引用ツイートを取得（API応答に含まれる）
    quote = tweet_raw.get("quote")
    if quote:
        quote_url = quote.get("url", "")
        quote_id = ""
        if quote_url:
            m = re.search(r'/status/(\d+)', quote_url)
            if m:
                quote_id = m.group(1)

        if quote_id and quote_id not in visited:
            visited.add(quote_id)
            quote_data = _parse_tweet_data(quote)
            result.append(quote_data)

            # 引用ツイートからさらに再帰
            nested = quote.get("quote")
            if nested:
                nested_url = nested.get("url", "")
                if nested_url:
                    result.extend(_collect_all_tweets_from_api(nested_url, visited, depth + 1))

            # 引用ツイートのテキスト中のX URLも再帰取得
            quote_text = quote.get("text", "")
            for linked_id in _extract_x_urls_from_text(quote_text):
                if linked_id not in visited:
                    linked_url = f"https://x.com/i/status/{linked_id}"
                    result.extend(_collect_all_tweets_from_api(linked_url, visited, depth + 1))

    # 2. テキスト中のX/Twitter URLを再帰取得
    text = tweet_raw.get("text", "")
    for linked_id in _extract_x_urls_from_text(text):
        if linked_id not in visited:
            linked_url = f"https://x.com/i/status/{linked_id}"
            result.extend(_collect_all_tweets_from_api(linked_url, visited, depth + 1))

    return result


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
            page.wait_for_selector('[data-testid="tweetText"]', timeout=15000)

            tweet_text_el = page.query_selector('[data-testid="tweetText"]')
            text = tweet_text_el.inner_text() if tweet_text_el else ""

            author_el = page.query_selector('[data-testid="User-Name"]')
            author_raw = author_el.inner_text() if author_el else ""
            author_parts = author_raw.split("\n") if author_raw else []
            author_name = author_parts[0].strip() if len(author_parts) > 0 else ""
            author_handle = ""
            for part in author_parts:
                if part.strip().startswith("@"):
                    author_handle = part.strip().lstrip("@")
                    break

            time_el = page.query_selector("time")
            timestamp = time_el.get_attribute("datetime") if time_el else ""

            images = []
            img_elements = page.query_selector_all('[data-testid="tweetPhoto"] img')
            for img in img_elements:
                src = img.get_attribute("src")
                if src and "pbs.twimg.com" in src:
                    src = re.sub(r'name=\w+', 'name=large', src)
                    images.append(src)

            return {
                "text": text,
                "author_name": author_name,
                "author_handle": author_handle,
                "timestamp": timestamp,
                "url": normalized_url,
                "images": images,
            }
        except Exception as e:
            print(f"Playwright取得エラー: {e}")
            return None
        finally:
            browser.close()


def _format_single_tweet(data: Dict) -> List[str]:
    """単一ポストのマークダウン行リストを生成"""
    author_name = data.get("author_name", "不明")
    author_handle = data.get("author_handle", "")
    text = data.get("text", "")
    timestamp = data.get("timestamp", "")
    tweet_url = data.get("url", "")
    images = data.get("images", [])

    lines = []
    lines.append(f"## {author_name} (@{author_handle})")
    if timestamp:
        lines.append(f"**投稿日時**: {timestamp}")
    if tweet_url:
        lines.append(f"**URL**: {tweet_url}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(text)
    lines.append("")

    if images:
        lines.append("### 添付画像")
        lines.append("")
        for i, img_url in enumerate(images, 1):
            lines.append(f"![画像{i}]({img_url})")
            lines.append("")

    return lines


def _format_all_tweets_as_markdown(tweets: List[Dict], original_url: str) -> Tuple[str, str]:
    """複数ポストをまとめてマークダウンに変換"""
    if not tweets:
        raise RuntimeError("取得したポストがありません")

    # タイトルは最初のツイート（元ツイート）から生成
    first = tweets[0]
    author_handle = first.get("author_handle", "")
    text = first.get("text", "")
    # タイトルから改行を除去
    title_text = re.sub(r'[\r\n]+', ' ', text).strip()
    if len(title_text) > 50:
        title = f"@{author_handle}: {title_text[:50]}..."
    else:
        title = f"@{author_handle}: {title_text}" if title_text else f"@{author_handle} のポスト"

    # マークダウン生成
    all_lines = []
    for i, tweet_data in enumerate(tweets):
        if i > 0:
            # 引用/リンク元ツイートの区切り
            all_lines.append("")
            all_lines.append("---")
            all_lines.append("")
            label = "引用元ツイート" if i == 1 else f"関連ツイート ({i})"
            all_lines.append(f"> **{label}**")
            all_lines.append("")

        all_lines.extend(_format_single_tweet(tweet_data))

    return (title, "\n".join(all_lines))


def fetch_x_post(url: str) -> Tuple[str, str]:
    """
    X/Twitterのポストを取得し、マークダウンとして返す
    引用ツイートやテキスト中のX URLも再帰的に取得する

    Tier1: fxtwitter API（高速・軽量・引用ツイート再帰対応）
    Tier2: Playwright（フォールバック、単一ツイートのみ）

    引数:
        url: X/TwitterのポストURL

    戻り値:
        tuple: (タイトル, マークダウンコンテンツ)
    """
    _extract_post_id(url)

    # Tier 1: fxtwitter API（再帰取得）
    print(f"fxtwitter APIで取得を試みます: {url}")
    tweets = _collect_all_tweets_from_api(url)

    if tweets:
        return _format_all_tweets_as_markdown(tweets, url)

    # Tier 2: Playwright フォールバック（単一ツイートのみ）
    print("fxtwitter APIでの取得に失敗。Playwrightで再試行します...")
    data = _fetch_via_playwright(url)

    if data is None:
        raise RuntimeError(
            f"X/Twitterポストの取得に失敗しました。"
            f"fxtwitter APIとPlaywrightの両方で取得できませんでした: {url}"
        )

    return _format_all_tweets_as_markdown([data], url)


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
