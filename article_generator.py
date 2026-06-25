import os
from openai import OpenAI
from typing import Optional

# OpenAI APIクライアントは必要になったタイミングで初期化する
# （YouTube処理を使わない通常URL登録でもBot起動できるようにする）
client = None


def get_openai_client():
    global client
    if client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEYが設定されていません。YouTube記事生成には環境変数が必要です。")
        client = OpenAI(api_key=api_key)
    return client


def generate_article_with_gpt5(
    transcript: str, 
    title: str, 
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
    model: str = "gpt-5"  # gpt-5, gpt-5-mini, gpt-5-nano
) -> Optional[str]:
    """
    GPT-5を使用してYouTube動画の字幕から構造化された記事を生成
    
    Args:
        transcript: 字幕テキスト
        title: 動画タイトル
        description: 動画の説明文（オプション）
        metadata: 動画のメタデータ（チャンネル名、タグなど）
        model: 使用するGPT-5モデル（gpt-5/gpt-5-mini/gpt-5-nano）
    
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
        if metadata.get('duration'):
            duration = metadata['duration']
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            if hours > 0:
                context_parts.append(f"動画の長さ: {hours}時間{minutes}分")
            else:
                context_parts.append(f"動画の長さ: {minutes}分")
    
    context = "\n".join(context_parts)
    
    # 字幕が長すぎる場合は制限（GPT-5は大容量入力に対応）
    max_transcript_length = 80000  # GPT-5は大容量入力に対応
    if len(transcript) > max_transcript_length:
        transcript = transcript[:max_transcript_length] + "...[以下省略]"
    
    # プロンプトの構築（GPT-5向けに最適化）
    prompt = f"""以下のYouTube動画の字幕から、読みやすく構造化された記事を作成してください。
この記事はゲーム開発者やマーケターが読むことを想定しています。

【要件】
1. 動画の核心となるメッセージを明確に抽出
2. 論理的な構造で情報を整理（導入→本論→結論）
3. 重要な洞察やアクションアイテムを強調
4. ゲーム開発・マーケティングの観点から実践的な価値を提供
5. 専門用語は適切に説明し、初心者にも理解しやすく
6. 具体例や数値データがあれば積極的に活用
7. 記事は日本語で、プロフェッショナルなトーンで作成

【動画情報】
{context}

【字幕テキスト】
{transcript}

【出力形式】
以下の構造でMarkdown形式の記事を作成してください：

# [魅力的で内容を的確に表すタイトル]

## 📌 エグゼクティブサマリー
[3-5文で動画の要点を簡潔にまとめる]

## 🎯 この記事で学べること
[箇条書きで3-5個の主要な学習ポイント]

## 📊 主要な内容

### [セクション1のタイトル]
[内容を詳しく説明]

### [セクション2のタイトル]
[内容を詳しく説明]

### [セクション3のタイトル]
[内容を詳しく説明]

## 💡 重要な洞察とポイント
[動画から得られる重要な洞察を箇条書きで]

## 🚀 実践への応用
[この内容をどのように実践に活かせるか]

## 📝 まとめ
[全体のまとめと次のアクション]

---
記事を作成してください："""

    try:
        # GPT-5で記事生成（Chat Completions API）
        print(f"GPT-5 ({model})を使用して記事を生成中...")
        
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_completion_tokens=128000  # GPT-5は最大128,000トークンまで対応
        )
        
        article = response.choices[0].message.content
        
        # 使用情報の出力
        if hasattr(response, 'usage'):
            usage = response.usage
            print(f"トークン使用量 - 入力: {usage.prompt_tokens}, 出力: {usage.completion_tokens}, 合計: {usage.total_tokens}")
            
            # GPT-5の推論トークンも表示（利用可能な場合）
            if hasattr(usage, 'reasoning_tokens'):
                print(f"推論トークン: {usage.reasoning_tokens}")
        
        print(f"GPT-5 ({model})での生成が完了しました")
        return article
        
    except Exception as e:
        print(f"記事生成中にエラーが発生しました: {e}")
        return None

def process_youtube_for_notion_gpt5(
    title: str,
    description: Optional[str],
    transcript: Optional[str],
    url: str,
    metadata: Optional[dict] = None,
    model: str = "gpt-5-mini"
) -> str:
    """
    YouTube動画情報を処理してNotion登録用コンテンツを生成（GPT-5使用）
    
    Args:
        title: 動画タイトル
        description: 動画説明文
        transcript: 字幕テキスト
        url: YouTube URL
        metadata: メタデータ
        model: 使用するGPT-5モデル（gpt-5/gpt-5-mini/gpt-5-nano）
    
    Returns:
        Notion登録用のコンテンツ
    """
    
    # 字幕から記事を生成
    article = None
    if transcript and len(transcript) > 100:  # 字幕が十分にある場合
        print("GPT-5で字幕から記事を生成中...")
        article = generate_article_with_gpt5(
            transcript=transcript,
            title=title,
            description=description,
            metadata=metadata,
            model=model
        )
        
        if article:
            print("GPT-5での記事生成が完了しました")
        else:
            print("記事の生成に失敗しました")
    
    # 記事と字幕を組み合わせてNotion用コンテンツを作成
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
        content_parts.append("# 🤖 AI分析記事（GPT-5生成）\n")
        content_parts.append(article)
        content_parts.append("\n---\n")
    
    # 元の字幕セクション（折りたたみ可能な形式で）
    if transcript:
        content_parts.append("# 📋 元の字幕（トランスクリプト）\n")
        content_parts.append("<details>")
        content_parts.append("<summary>クリックして字幕を表示</summary>\n")
        
        # 長い字幕は分割して表示
        if len(transcript) > 30000:
            content_parts.append(transcript[:30000])
            content_parts.append("\n\n*[字幕が長いため、残りの部分は省略されています]*")
        else:
            content_parts.append(transcript)
        
        content_parts.append("\n</details>")
    elif not article:
        # 記事も字幕もない場合
        content_parts.append("*字幕の取得に失敗しました。動画の説明文のみが利用可能です。*")
    
    return "\n".join(content_parts)

def process_youtube_for_notion(
    title: str,
    description: Optional[str],
    transcript: Optional[str],
    url: str,
    metadata: Optional[dict] = None,
    use_best_model: bool = True  # 最良のモデルを使用
) -> str:
    """
    YouTube動画情報を処理してNotion登録用コンテンツを生成
    
    主要な処理フロー:
    1. 字幕がある場合は記事を生成
    2. 記事と字幕を組み合わせる
    3. Notion登録用の形式で返す
    """
    
    return process_youtube_for_notion_gpt5(
        title=title,
        description=description,
        transcript=transcript,
        url=url,
        metadata=metadata,
        model="gpt-5"  # デフォルトでgpt-5-miniを使用
    )


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