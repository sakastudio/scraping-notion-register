import os
from typing import Optional
from openai import OpenAI

# OpenAI API設定
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

def translate_title(title: str, source_lang: str = "en", target_lang: str = "ja") -> Optional[str]:
    """
    OpenAI APIを使用してタイトルを翻訳する
    
    引数:
        title: 翻訳するタイトル
        source_lang: 元の言語コード（デフォルト: "en"）
        target_lang: 翻訳先の言語コード（デフォルト: "ja"）
        
    戻り値:
        str: 翻訳されたタイトル、または翻訳に失敗した場合はNone
    """
    if not OPENAI_API_KEY:
        print("警告: OPENAI_API_KEYが設定されていません。タイトル翻訳はスキップします。")
        return None
    
    if not title:
        print("警告: 翻訳するタイトルが指定されていません。")
        return None
    
    # 既に対象言語の可能性があるかチェック（簡易的）
    if target_lang == "ja" and any([ord(c) > 0x3000 for c in title]):
        print(f"タイトルは既に日本語の可能性があります: {title}")
        return None
    
    # クライアントの初期化
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": f"あなたは優秀な{source_lang}から{target_lang}への翻訳者です。与えられたテキストを適切に翻訳してください。翻訳のみを返し、余計な説明は不要です。"},
                {"role": "user", "content": f"以下のタイトルを翻訳してください：\n{title}"}
            ],
            temperature=0.3,
            max_tokens=100
        )
        
        # レスポンスから翻訳文を抽出
        translated_title = response.choices[0].message.content.strip()
        
        print(f"タイトル翻訳: {title} -> {translated_title}")
        return translated_title
        
    except Exception as e:
        print(f"タイトル翻訳中にエラーが発生しました: {e}")
        return None


def is_non_japanese_title(title: str) -> bool:
    """
    タイトルが日本語以外の言語（主に英語）かどうかを判定
    
    引数:
        title: 判定するタイトル
        
    戻り値:
        bool: 日本語以外と判定された場合はTrue
    """
    # 日本語文字（ひらがな、カタカナ、漢字など）の含有率を計算
    jp_chars = 0
    for c in title:
        # 日本語の文字コード範囲をチェック
        if ord(c) > 0x3000:  # 日本語文字のUnicode範囲（簡易判定）
            jp_chars += 1
    
    # 日本語文字が20%未満の場合、日本語以外と判定
    jp_ratio = jp_chars / len(title) if title else 0
    return jp_ratio < 0.2


if __name__ == "__main__":
    # テスト用
    test_titles = [
        "Breaking News: Major Technological Breakthrough Announced",
        "The Future of Artificial Intelligence in Healthcare",
        "How to Improve Your Productivity While Working from Home",
        "日本語のタイトル：人工知能の未来について",
    ]
    
    for title in test_titles:
        print(f"\n元タイトル: {title}")
        print(f"日本語以外のタイトル判定: {is_non_japanese_title(title)}")
        
        if is_non_japanese_title(title):
            translated = translate_title(title)
            print(f"翻訳結果: {translated}")
        else:
            print("翻訳不要")