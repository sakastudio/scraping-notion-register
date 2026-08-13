import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse


DEFAULT_RULES_FILE = Path(__file__).with_name("url_preprocessing_rules.json")


@dataclass(frozen=True)
class URLPreprocessingRules:
    """URL登録前処理ルール。必要になったらフィールドを増やして拡張する。"""

    strip_query_and_fragment_hosts: frozenset[str]


def _normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def load_url_preprocessing_rules(path: str | Path = DEFAULT_RULES_FILE) -> URLPreprocessingRules:
    """JSONのドメインリストからURL前処理ルールを読み込む。"""
    rules_path = Path(path)
    with rules_path.open("r", encoding="utf-8") as f:
        raw_rules = json.load(f)

    strip_hosts = frozenset(
        host
        for host in (
            _normalize_host(str(item))
            for item in raw_rules.get("strip_query_and_fragment_hosts", [])
        )
        if host
    )
    return URLPreprocessingRules(strip_query_and_fragment_hosts=strip_hosts)


def preprocess_registration_url(
    url: str,
    rules: URLPreprocessingRules | None = None,
) -> str:
    """Notion登録前にURLを正規化する共通入口。"""
    if rules is None:
        rules = load_url_preprocessing_rules()

    try:
        parsed = urlparse(url)
    except Exception:
        return url

    hostname = _normalize_host(parsed.hostname or "")
    if hostname in {"speakerdeck.com", "www.speakerdeck.com"}:
        path = parsed.path.rstrip("/") or "/"
        return urlunparse(("https", "speakerdeck.com", path, "", "", ""))
    if hostname in rules.strip_query_and_fragment_hosts:
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            "",  # query
            "",  # fragment
        ))

    return url


# 既存コード・テストからの呼び名互換。
def normalize_registration_url(url: str) -> str:
    return preprocess_registration_url(url)
