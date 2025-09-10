import re
import yt_dlp
import requests
from typing import Optional, Tuple, Dict, Any, List
import re
from typing import Optional, Tuple, Dict, Any, List

import requests
import yt_dlp


def extract_video_id(url: str) -> Optional[str]:
    """YouTube URLから動画IDを抽出"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def parse_vtt_subtitle(vtt_content: str) -> str:
    """VTT形式の字幕をテキストにパース"""
    lines = vtt_content.split('\n')
    text_lines = []
    
    # VTTヘッダーをスキップ
    start_index = 0
    for i, line in enumerate(lines):
        if 'WEBVTT' in line:
            start_index = i + 1
            break
    
    # タイムスタンプと設定行をスキップしてテキストのみを抽出
    i = start_index
    while i < len(lines):
        line = lines[i].strip()
        
        # タイムスタンプ行をスキップ（00:00:00.000 --> 00:00:05.000 形式）
        if '-->' in line:
            i += 1
            # 次の空行またはタイムスタンプまでのテキストを収集
            while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                text = lines[i].strip()
                # HTMLタグを除去（<c>タグなど）
                text = re.sub(r'<[^>]+>', '', text)
                # 重複を避ける
                if text and (not text_lines or text != text_lines[-1]):
                    text_lines.append(text)
                i += 1
        i += 1
    
    return ' '.join(text_lines)

def parse_srt_subtitle(srt_content: str) -> str:
    """SRT形式の字幕をテキストにパース"""
    lines = srt_content.split('\n')
    text_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # タイムスタンプ行を検出（00:00:00,000 --> 00:00:05,000 形式）
        if '-->' in line:
            i += 1
            # 次の空行または番号行までのテキストを収集
            while i < len(lines) and lines[i].strip() and not lines[i].strip().isdigit() and '-->' not in lines[i]:
                text = lines[i].strip()
                # HTMLタグを除去
                text = re.sub(r'<[^>]+>', '', text)
                # 重複を避ける
                if text and (not text_lines or text != text_lines[-1]):
                    text_lines.append(text)
                i += 1
        i += 1
    
    return ' '.join(text_lines)

def download_and_parse_subtitle(subtitle_url: str, format_type: str = 'vtt') -> Optional[str]:
    """字幕URLからテキストをダウンロードしてパース"""
    try:
        response = requests.get(subtitle_url, timeout=10)
        response.raise_for_status()
        content = response.text
        
        # フォーマットに応じてパース
        if format_type == 'vtt' or 'vtt' in subtitle_url:
            return parse_vtt_subtitle(content)
        elif format_type == 'srt':
            return parse_srt_subtitle(content)
        else:
            # その他のフォーマットは生テキストとして返す
            return content
            
    except Exception as e:
        print(f"字幕のダウンロード/パースエラー: {e}")
        return None

def get_best_subtitle(subtitles_dict: Dict, preferred_langs: List[str] = ['ja', 'en']) -> Optional[Tuple[str, Dict]]:
    """利用可能な字幕から最適なものを選択"""
    if not subtitles_dict:
        return None
    
    # 優先言語順に探す
    for lang in preferred_langs:
        if lang in subtitles_dict:
            subtitle_list = subtitles_dict[lang]
            # vtt形式を優先、次にsrt、その他
            for fmt_priority in ['vtt', 'srt', 'srv3', 'srv2', 'srv1', 'json3']:
                for subtitle_info in subtitle_list:
                    if subtitle_info.get('ext') == fmt_priority:
                        return lang, subtitle_info
            
            # 形式の優先順位で見つからない場合は最初のものを返す
            if subtitle_list:
                return lang, subtitle_list[0]
    
    # 優先言語がない場合は最初の利用可能な言語を返す
    for lang, subtitle_list in subtitles_dict.items():
        if subtitle_list:
            return lang, subtitle_list[0]
    
    return None

def fetch_youtube_info(url: str, cookies_file: str = "youtube_com_cookies.txt") -> Tuple[Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    """
    YouTube動画の情報と字幕を取得（yt-dlpのみ使用）
    
    引数:
        url: YouTube動画のURL
        cookies_file: YouTube認証用のcookiesファイルパス
    
    戻り値:
        tuple: (タイトル, 説明文, 字幕テキスト, メタデータ辞書)
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"無効なYouTube URL: {url}")
    
    # yt-dlpのオプション設定
    ydl_opts = {
        'quiet': False,  # デバッグのため一時的にFalse
        'no_warnings': False,
        'skip_download': True,
        # 字幕関連のオプション
        'writesubtitles': True,  # 手動字幕を取得
        'writeautomaticsub': True,  # 自動生成字幕を取得
        'subtitleslangs': ['ja', 'en'],  # 優先言語
    }
    
    # cookiesファイルが存在する場合は使用
    import os
    if os.path.exists(cookies_file):
        ydl_opts['cookiesfrombrowser'] = None  # ブラウザのcookieを使わない
        ydl_opts['cookiefile'] = cookies_file
        print(f"Cookieファイルを使用: {cookies_file}")
    
    title = None
    description = None
    metadata = {}
    transcript = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 動画情報を取得
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        # フォーマットエラーの場合は、フォーマット指定なしで再試行
        if "Requested format is not available" in str(e):
            print("フォーマットエラーを回避して再試行...")
            ydl_opts['format'] = None  # フォーマット指定を削除
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        else:
            raise

    # 基本情報を取得
    title = info.get('title', '')
    description = info.get('description', '')

    # メタデータを収集
    metadata = {
        'channel': info.get('uploader', ''),
        'channel_id': info.get('channel_id', ''),
        'duration': info.get('duration', 0),
        'view_count': info.get('view_count', 0),
        'like_count': info.get('like_count', 0),
        'upload_date': info.get('upload_date', ''),
        'tags': info.get('tags', []),
        'categories': info.get('categories', []),
        'thumbnail': info.get('thumbnail', ''),
        'video_id': video_id,
        'url': url
    }

    # 字幕を取得
    print(f"利用可能な字幕を確認中...")

    # 手動字幕を優先的に取得
    subtitles = info.get('subtitles', {})
    subtitle_info = None
    subtitle_lang = None

    if subtitles:
        print(f"手動字幕が利用可能: {list(subtitles.keys())}")
        result = get_best_subtitle(subtitles, ['ja', 'en'])
        if result:
            subtitle_lang, subtitle_info = result

    # 手動字幕がない場合は自動生成字幕を取得
    if not subtitle_info:
        auto_captions = info.get('automatic_captions', {})
        if auto_captions:
            print(f"自動生成字幕が利用可能: {list(auto_captions.keys())}")
            result = get_best_subtitle(auto_captions, ['ja', 'en'])
            if result:
                subtitle_lang, subtitle_info = result

    # 字幕をダウンロードしてパース
    if subtitle_info and 'url' in subtitle_info:
        print(f"字幕をダウンロード中... (言語: {subtitle_lang}, 形式: {subtitle_info.get('ext', 'unknown')})")
        transcript = download_and_parse_subtitle(
            subtitle_info['url'],
            subtitle_info.get('ext', 'vtt')
        )

        if transcript:
            print(f"字幕の取得に成功しました（{len(transcript)}文字）")
        else:
            print("字幕のパースに失敗しました")
    else:
        print("利用可能な字幕が見つかりませんでした")


    return title, description, transcript, metadata

def format_youtube_content(title: str, description: str, transcript: str, metadata: Dict[str, Any]) -> str:
    """
    YouTube動画の情報をMarkdown形式で整形
    """
    content_parts = []
    
    # 動画情報セクション
    content_parts.append("## 動画情報")
    content_parts.append(f"**タイトル**: {title}")
    content_parts.append(f"**チャンネル**: {metadata.get('channel', '不明')}")
    content_parts.append(f"**公開日**: {metadata.get('upload_date', '不明')}")
    content_parts.append(f"**再生回数**: {metadata.get('view_count', 0):,}")
    content_parts.append(f"**高評価数**: {metadata.get('like_count', 0):,}")
    
    duration = metadata.get('duration', 0)
    if duration:
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60
        if hours > 0:
            content_parts.append(f"**動画の長さ**: {hours}時間{minutes}分{seconds}秒")
        else:
            content_parts.append(f"**動画の長さ**: {minutes}分{seconds}秒")
    
    if metadata.get('tags'):
        content_parts.append(f"**タグ**: {', '.join(metadata['tags'][:10])}")
    
    content_parts.append("")
    
    # 説明文セクション
    if description:
        content_parts.append("## 説明文")
        content_parts.append(description[:1000])  # 最初の1000文字
        if len(description) > 1000:
            content_parts.append("...")
        content_parts.append("")
    
    # 字幕セクション
    if transcript:
        content_parts.append("## 字幕・トランスクリプト")
        # 長い字幕は適切に分割
        if len(transcript) > 5000:
            content_parts.append(transcript[:5000])
            content_parts.append("\n[字幕が長いため省略されています...]")
        else:
            content_parts.append(transcript)
    else:
        content_parts.append("## 字幕・トランスクリプト")
        content_parts.append("*字幕が利用できません*")
    
    return "\n".join(content_parts)

if __name__ == "__main__":
    # テスト用
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Never Gonna Give You Up
        "https://youtu.be/dQw4w9WgXcQ",
    ]
    
    for test_url in test_urls[:1]:  # 最初の1つだけテスト
        print(f"\nテスト URL: {test_url}")
        print("-" * 50)
        
        try:
            title, description, transcript, metadata = fetch_youtube_info(test_url)
            
            if title:
                print(f"✅ タイトル: {title}")
                print(f"📝 説明文の長さ: {len(description) if description else 0}文字")
                print(f"📄 字幕の長さ: {len(transcript) if transcript else 0}文字")
                print(f"📺 チャンネル: {metadata.get('channel', '不明')}")
                print(f"👁️ 再生回数: {metadata.get('view_count', 0):,}")
                
                # Markdown形式で保存
                content = format_youtube_content(title, description, transcript, metadata)
                with open("youtube_test.md", "w", encoding="utf-8") as f:
                    f.write(content)
                print("\n📁 youtube_test.md に保存しました")
                
                # 字幕の最初の部分を表示
                if transcript:
                    print("\n字幕の最初の部分:")
                    print("-" * 30)
                    print(transcript[:500] + "..." if len(transcript) > 500 else transcript)
            else:
                print("❌ 動画情報の取得に失敗しました")
                
        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()