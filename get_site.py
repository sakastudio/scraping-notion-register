import os
import json
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
from urllib.parse import urljoin


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

    # ----------------------------- #
    # 1) セッションの作成 & クッキー読み込み
    # ----------------------------- #
    session = requests.Session()
    with open(cookie_file_path, 'r', encoding='utf-8') as f:
        cookies_data = json.load(f)
    for cookie in cookies_data:
        session.cookies.set(
            name=cookie['name'],
            value=cookie['value'],
            domain=cookie.get('domain'),
            path=cookie.get('path', '/')
        )

    # ----------------------------- #
    # 2) URL から HTML を取得
    # ----------------------------- #
    response = session.get(url)
    if response.status_code != 200:
        print(f"Failed to retrieve {url} (status code: {response.status_code})")
        return
    html_content = response.text

    # ----------------------------- #
    # 3) HTML をパースしてタイトルとメインコンテンツを抽出
    # ----------------------------- #
    soup = BeautifulSoup(html_content, "html.parser")
    
    # サイトのタイトルを取得
    page_title = ""
    if soup.title:
        page_title = soup.title.string.strip()
    
    # メインコンテンツの抽出 - 一般的なパターンを試みる
    main_content = None
    
    # 一般的なコンテンツコンテナのセレクタを試す
    potential_selectors = [
        "article", 
        "main", 
        ".content", 
        ".post-content", 
        ".article-content",
        ".entry-content",
        "#content",
        ".main-content",
        ".post",
        ".article"
    ]
    
    for selector in potential_selectors:
        if selector.startswith("."):
            # クラスセレクタ
            elements = soup.find_all(class_=selector[1:])
        elif selector.startswith("#"):
            # IDセレクタ
            element = soup.find(id=selector[1:])
            elements = [element] if element else []
        else:
            # タグセレクタ
            elements = soup.find_all(selector)
        
        if elements:
            # 最も内容が多い要素を選択
            elements_with_content = [(el, len(str(el))) for el in elements]
            elements_with_content.sort(key=lambda x: x[1], reverse=True)
            main_content = elements_with_content[0][0]
            break
    
    # メインコンテンツが見つからない場合はbody全体を使用
    if not main_content:
        main_content = soup.body if soup.body else soup
    
    # ----------------------------- #
    # 4) 余分な要素を削除
    # ----------------------------- #
    # ナビゲーション、サイドバー、フッター、広告などの不要な要素を削除
    unwanted_elements = [
        'nav', 'footer', '.sidebar', '.ad', '.advertisement', 
        '.banner', '.header', '.menu', '.navigation', '.comment', 
        '.comments', '.social', '.share', '.related'
    ]
    
    for selector in unwanted_elements:
        if selector.startswith('.'):
            # クラスセレクタ
            for element in main_content.find_all(class_=selector[1:]):
                element.decompose()
        else:
            # タグセレクタ
            for element in main_content.find_all(selector):
                element.decompose()
    
    # ----------------------------- #
    # 5) HTML をマークダウンに変換
    # ----------------------------- #
    markdown_content = markdownify(
        str(main_content),
        heading_style="ATX"
    )
    
    # 連続する空行を削減
    import re
    markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content)
    
    # タイトルとマークダウンコンテンツをタプルとして返す
    return (page_title, markdown_content)


if __name__ == "__main__":
    # 使い方例
    test_url = "https://newsletter.gamediscover.co/p/steams-top-grossing-games-of-2024"
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
