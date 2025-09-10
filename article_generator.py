import os
from openai import OpenAI
from typing import Optional

# OpenAI APIクライアントの初期化
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def generate_article_from_transcript(
    transcript: str, 
    title: str, 
    description: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Optional[str]:
    """
    YouTube動画の字幕から構造化された記事を生成
    
    Args:
        transcript: 字幕テキスト
        title: 動画タイトル
        description: 動画の説明文（オプション）
        metadata: 動画のメタデータ（チャンネル名、タグなど）
    
    Returns:
        生成された記事テキスト
    """
    
    if not transcript:
        return None
    
    # コンテキスト情報を構築
    context_parts = [f"動画タイトル: {title}"]
    
    if description:
        context_parts.append(f"動画説明文: {description[:500]}")
    
    if metadata:
        if metadata.get('channel'):
            context_parts.append(f"チャンネル: {metadata['channel']}")
        if metadata.get('tags'):
            context_parts.append(f"タグ: {', '.join(metadata['tags'][:5])}")
    
    context = "\n".join(context_parts)
    
    # 字幕が長すぎる場合は制限
    max_transcript_length = 10000
    if len(transcript) > max_transcript_length:
        transcript = transcript[:max_transcript_length] + "...[以下省略]"
    
    # プロンプトの構築
    prompt = f"""以下のYouTube動画の字幕から、読みやすく構造化された記事を作成してください。

【要件】
1. 動画の主要なポイントを整理して説明
2. 適切な見出しとセクション分けを行う
3. 重要な情報は箇条書きでまとめる
4. ゲーム開発やマーケティングの観点から有用な洞察があれば追加
5. 専門用語は必要に応じて簡潔に説明
6. 記事は日本語で作成

【動画情報】
{context}

【字幕テキスト】
{transcript}

【出力形式】
Markdown形式で、以下の構造を参考に記事を作成してください：

# [記事タイトル]

## 概要
[動画の内容を2-3文で要約]

## 主要なポイント
[重要な内容を箇条書きで]

## 詳細な内容
[セクションごとに詳しく説明]

## まとめ
[全体のまとめと重要な takeaway]

---
記事を作成してください："""

    try:
        # OpenAI APIを呼び出し
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "あなたは優秀なテクニカルライターです。YouTube動画の内容を分かりやすい記事にまとめることが得意です。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        # 生成された記事を取得
        article = response.choices[0].message.content
        
        return article
        
    except Exception as e:
        print(f"記事生成中にエラーが発生しました: {e}")
        return None

def combine_article_and_transcript(
    article: Optional[str], 
    transcript: Optional[str],
    title: str,
    url: str,
    metadata: Optional[dict] = None
) -> str:
    """
    生成された記事と元の字幕を組み合わせてNotionに登録する形式にする
    
    Args:
        article: 生成された記事
        transcript: 元の字幕
        title: 動画タイトル
        url: YouTube URL
        metadata: 動画のメタデータ
    
    Returns:
        Notion登録用の完全なコンテンツ
    """
    
    content_parts = []
    
    # URLとメタデータ
    content_parts.append(f"**YouTube URL**: {url}\n")
    
    if metadata:
        if metadata.get('channel'):
            content_parts.append(f"**チャンネル**: {metadata['channel']}")
        if metadata.get('upload_date'):
            content_parts.append(f"**公開日**: {metadata['upload_date']}")
        if metadata.get('view_count'):
            content_parts.append(f"**再生回数**: {metadata['view_count']:,}")
        content_parts.append("")
    
    # 生成された記事セクション
    if article:
        content_parts.append("---\n")
        content_parts.append("# 📝 AIが生成した記事\n")
        content_parts.append(article)
        content_parts.append("\n---\n")
    
    # 元の字幕セクション
    if transcript:
        content_parts.append("# 📋 元の字幕（トランスクリプト）\n")
        
        # 長い字幕は分割して表示
        if len(transcript) > 15000:
            content_parts.append(transcript[:15000])
            content_parts.append("\n\n*[字幕が長いため、残りの部分は省略されています]*")
        else:
            content_parts.append(transcript)
    elif not article:
        # 記事も字幕もない場合
        content_parts.append("*字幕の取得に失敗しました。動画の説明文のみが利用可能です。*")
    
    return "\n".join(content_parts)

def process_youtube_for_notion(
    title: str,
    description: Optional[str],
    transcript: Optional[str],
    url: str,
    metadata: Optional[dict] = None
) -> str:
    """
    YouTube動画情報を処理してNotion登録用コンテンツを生成
    
    主要な処理フロー:
    1. 字幕がある場合は記事を生成
    2. 記事と字幕を組み合わせる
    3. Notion登録用の形式で返す
    """
    
    # 字幕から記事を生成
    article = None
    if transcript and len(transcript) > 100:  # 字幕が十分にある場合
        print("字幕から記事を生成中...")
        article = generate_article_from_transcript(
            transcript=transcript,
            title=title,
            description=description,
            metadata=metadata
        )
        
        if article:
            print("記事の生成が完了しました")
        else:
            print("記事の生成に失敗しました")
    elif description and len(description) > 200:  # 字幕がない場合は説明文から生成
        print("説明文から記事を生成中...")
        article = generate_article_from_transcript(
            transcript=description,  # 説明文を字幕の代わりに使用
            title=title,
            description=None,
            metadata=metadata
        )
    
    # 記事と字幕を組み合わせてNotion用コンテンツを作成
    content = combine_article_and_transcript(
        article=article,
        transcript=transcript,
        title=title,
        url=url,
        metadata=metadata
    )
    
    return content

if __name__ == "__main__":
    # テスト用
    test_transcript = """
    こんにちは、今日はゲーム開発における重要なポイントについて話します。
    まず第一に、プレイヤーの体験を最優先に考えることが大切です。
    ゲームメカニクスは面白さを生み出す手段であって、目的ではありません。
    次に、プロトタイピングの重要性について説明します。
    早期にプロトタイプを作成し、実際にプレイしてフィードバックを得ることが成功への鍵です。
    """
    
    test_metadata = {
        'channel': 'ゲーム開発チャンネル',
        'tags': ['ゲーム開発', 'Unity', 'インディーゲーム'],
        'view_count': 12345,
        'upload_date': '2024-01-15'
    }
    
    # 記事生成のテスト
    content = process_youtube_for_notion(
        title="ゲーム開発の基本原則",
        description="このビデオでは、成功するゲーム開発のための基本的な原則について解説します。",
        transcript=test_transcript,
        url="https://youtube.com/watch?v=example",
        metadata=test_metadata
    )
    
    # 結果を保存
    with open("article_test.md", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("テスト記事を article_test.md に保存しました")