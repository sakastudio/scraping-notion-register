import os
from typing import List

from openai import OpenAI

# OpenAI API設定
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def load_tags_from_file(file_path: str = "tags.txt") -> List[str]:
    """
    タグリストをファイルから読み込む
    
    引数:
        file_path: タグリストが保存されているファイルパス
        
    戻り値:
        List[str]: タグのリスト
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tags = [line.strip() for line in f.readlines() if line.strip()]
        return tags
    except FileNotFoundError:
        print(f"警告: {file_path} が見つかりません。空のタグリストを返します。")
        return []


def predict_tags(content: str, title: str, available_tags: List[str], max_tags: int = 5) -> List[str]:
    """
    OpenAI APIを使用してコンテンツからタグを予測
    
    引数:
        content: 分析するコンテンツ（マークダウン形式）
        title: コンテンツのタイトル
        available_tags: 使用可能なタグのリスト
        max_tags: 最大タグ数（デフォルト: 5）
        
    戻り値:
        List[str]: 予測されたタグのリスト
    """
    if not OPENAI_API_KEY:
        print("警告: OPENAI_API_KEYが設定されていません。タグ予測はスキップします。")
        return []
    
    if not available_tags:
        print("警告: 使用可能なタグが見つかりません。タグ予測はスキップします。")
        return []
    
    # クライアントの初期化
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # コンテンツの最初の部分だけを使用（APIの文字数制限のため）
    trimmed_content = content[:3000] if len(content) > 3000 else content
    
    try:
        # 使用可能なタグをカンマ区切りで結合
        tags_str = ", ".join(available_tags)
        
        # GPT-3.5 Turbo APIを呼び出し
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": f"あなたはコンテンツに適したタグを選択する専門家です。以下のタグリストからコンテンツに最も関連するタグを選んでください: {tags_str}"},
                {"role": "user", "content": f"タイトル: {title}\n\nコンテンツ: {trimmed_content}\n\nこのコンテンツに最適なタグを{max_tags}個以内で選んでください。タグはカンマ区切りのリストとして返してください。提示されたタグリスト以外のタグは使用しないでください。"}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        # レスポンスからタグを抽出
        tags_text = response.choices[0].message.content.strip()
        
        # カンマ区切りでタグを分割
        predicted_tags = [tag.strip() for tag in tags_text.split(',')]
        
        # 使用可能なタグと照合（APIが提案外のタグを返した場合に除外）
        valid_tags = [tag for tag in predicted_tags if tag in available_tags]
        
        # 最大数に制限
        return valid_tags[:max_tags]
        
    except Exception as e:
        print(f"タグ予測中にエラーが発生しました: {e}")
        return []


if __name__ == "__main__":
    # テスト用
    
    # タグリストの読み込み
    available_tags = load_tags_from_file()
    print(f"読み込まれたタグ: {available_tags}")
    
    # テスト用のコンテンツ
    with open("downloaded/output.md", "r", encoding="utf-8") as f:
        test_content = f.read()
    
    # テスト用のタイトル
    test_title = "Steam's top-grossing games of 2024 revealed, analyzed"
    
    # タグ予測の実行
    if available_tags:
        predicted_tags = predict_tags(test_content, test_title, available_tags)
        print(f"予測されたタグ: {predicted_tags}")
    else:
        print("タグが読み込まれなかったため、テストをスキップします。")