import os
import re
import json
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
from urllib.parse import urljoin, urlparse


def fetch_and_save_content(
        url: str,
        cookie_file_path: str = "cookies.json",
        download_folder: str = "downloaded"
):
    """
    指定した URL からクッキーを使用して HTML を取得し、
    画像をローカルにダウンロードした上で HTML を Markdown に変換し、
    「downloaded」フォルダに保存するサンプルコードです。

    改善点:
        1. 画像のファイル名が URL そのままにならないように調整
        2. マークダウン内に 画像が ![alt](path) 形式で埋め込まれるように設定

    引数:
        url: データを取得するURL
        cookie_file_path: ブラウザでエクスポートした JSON 形式のクッキーファイル
        download_folder: 保存先のフォルダ (デフォルト: "downloaded")
    """
    # 保存先フォルダの作成（存在しない場合は作成）
    os.makedirs(download_folder, exist_ok=True)

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
    # 3) HTML をパース & 画像の収集
    # ----------------------------- #
    soup = BeautifulSoup(html_content, "html.parser")
    img_tags = soup.find_all("img")

    # { 元の src: ローカルに保存したファイル名 } の対応表
    local_src_map = {}

    # ----------------------------- #
    # 4) 画像のダウンロード & ファイル名調整
    # ----------------------------- #
    # 画像タグを順に処理してダウンロード
    for i, img_tag in enumerate(img_tags, start=1):
        src = img_tag.get("src")
        if not src:
            continue

        # 画像URLを絶対URLに変換 (相対パスに対応)
        img_url = urljoin(url, src)
        parsed_url = urlparse(img_url)

        # パスからファイル名を取得 (例: /images/pic.jpg -> pic.jpg)
        file_name = os.path.basename(parsed_url.path)

        # クエリ(?以降)やフラグメント(#以降)があれば除去
        file_name = file_name.split('?')[0]
        file_name = file_name.split('#')[0]

        # ファイル名が空の場合は連番で命名
        if not file_name:
            file_name = f"image_{i}.jpg"

        # OSのファイル名に使用できない文字を置換
        file_name = re.sub(r'[\\/:*?"<>|]', '_', file_name)

        # 拡張子が無ければ .jpg を付与
        root, ext = os.path.splitext(file_name)
        if not ext:
            ext = ".jpg"
            file_name = root + ext

        # ダウンロード先ファイルパス
        local_image_path = os.path.join(download_folder, file_name)

        # クッキー付きセッションで画像をダウンロード
        img_resp = session.get(img_url)
        if img_resp.status_code == 200:
            with open(local_image_path, "wb") as f:
                f.write(img_resp.content)
            local_src_map[src] = file_name
        else:
            print(f"Failed to download image: {img_url} (status code: {img_resp.status_code})")

    # ----------------------------- #
    # 5) HTML 内の画像パスをローカルパスに置換
    #    かつ alt 属性が無い画像タグにはファイル名を付与
    # ----------------------------- #
    for original_src, local_file_name in local_src_map.items():
        for img_tag in soup.find_all("img", src=original_src):
            # alt がなければファイル名を入れておく（Markdown の ![alt](src) に出る）
            if not img_tag.get("alt"):
                img_tag["alt"] = local_file_name
            img_tag["src"] = local_file_name

    # 置換後の HTML
    updated_html = str(soup)

    # ----------------------------- #
    # 6) HTML をマークダウンに変換
    #    convert=['img'] で imgタグを ![alt](src) に変換
    # ----------------------------- #
    markdown_content = markdownify(
        updated_html,
        heading_style="ATX",
        convert=['img']
    )

    # ----------------------------- #
    # 7) マークダウンファイルの保存
    # ----------------------------- #
    md_file_path = os.path.join(download_folder, "output.md")
    with open(md_file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"Markdown file saved at: {md_file_path}")
    print(f"Images saved in: {download_folder}")


if __name__ == "__main__":
    # 使い方例
    test_url = "https://newsletter.gamediscover.co/p/steams-top-grossing-games-of-2024"
    cookie_file = "cookies.json"  # クッキーファイル（JSON形式）
    fetch_and_save_content(test_url, cookie_file)
