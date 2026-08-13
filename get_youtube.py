"""YouTube metadata and complete transcript acquisition."""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
import yt_dlp
try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
MAX_TRANSCRIPT_CHARS = 100_000


def extract_video_id(url: str) -> Optional[str]:
    """Extract an ID only from an allow-listed, structurally valid YouTube URL."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"}:
            return None
        candidate = None
        if host in _SHORT_HOSTS:
            candidate = parsed.path.strip("/").split("/", 1)[0]
        elif host in _YOUTUBE_HOSTS:
            if parsed.path.rstrip("/") == "/watch":
                candidate = parse_qs(parsed.query).get("v", [None])[0]
            else:
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
                    candidate = parts[1]
        return candidate if candidate and _VIDEO_ID_RE.fullmatch(candidate) else None
    except (TypeError, ValueError):
        return None


def canonical_youtube_url(url: str) -> str:
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("無効なYouTube URLです")
    return f"https://www.youtube.com/watch?v={video_id}"


def _format_choice(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for ext in ("json3", "vtt", "srt", "srv3", "srv2", "srv1"):
        for entry in entries or []:
            if entry.get("ext") == ext and entry.get("url"):
                return entry
    return next((x for x in (entries or []) if x.get("url")), None)


def select_preferred_subtitle(subtitles: Dict[str, List[Dict]], automatic: Dict[str, List[Dict]]):
    """Select manual-ja, auto-ja, manual-en, auto-en, including locales."""
    for source, base, is_auto in ((subtitles,"ja",False),(automatic,"ja",True),(subtitles,"en",False),(automatic,"en",True)):
        for language in sorted(source, key=lambda key: (key != base, key)):
            if language == base or language.startswith(base + "-") or language.startswith(base + "_"):
                choice = _format_choice(source.get(language, []))
                if choice:
                    return choice, language, is_auto
    return None


def _public_transcript(video_id: str):
    """Use YouTube's public transcript surface when signed media URLs are blocked."""
    if YouTubeTranscriptApi is None:
        raise RuntimeError("youtube-transcript-api is not installed")
    transcripts = list(YouTubeTranscriptApi().list(video_id))
    for language, generated in (("ja", False), ("ja", True), ("en", False), ("en", True)):
        for item in sorted(transcripts, key=lambda value: (value.language_code != language, value.language_code)):
            code = item.language_code
            if (code == language or code.startswith(language + "-") or code.startswith(language + "_")) and item.is_generated == generated:
                text = "\n".join(segment.text for segment in item.fetch()).strip()
                if text:
                    return text, code, generated
    raise RuntimeError("利用可能な日本語または英語字幕がありません")


def _watch_page_metadata(canonical: str) -> Dict[str, Any]:
    response = requests.get(canonical + "&hl=ja", timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    marker = "ytInitialPlayerResponse = "
    position = response.text.find(marker)
    if position < 0:
        raise RuntimeError("YouTube player metadata was unavailable")
    start = response.text.find("{", position + len(marker))
    data, _ = json.JSONDecoder().raw_decode(response.text[start:])
    details = data.get("videoDetails") or {}
    micro = (data.get("microformat") or {}).get("playerMicroformatRenderer") or {}
    thumbnails = (details.get("thumbnail") or {}).get("thumbnails") or [{}]
    return {
        "title": details.get("title", ""), "description": details.get("shortDescription", ""),
        "uploader": details.get("author", ""), "channel_id": details.get("channelId", ""),
        "duration": int(details.get("lengthSeconds") or 0), "view_count": int(details.get("viewCount") or 0),
        "upload_date": (micro.get("uploadDate") or "").replace("-", ""),
        "thumbnail": thumbnails[-1].get("url", ""), "tags": details.get("keywords") or [],
    }


def parse_json3_subtitle(content: str) -> str:
    data = json.loads(content)
    pieces = []
    for event in data.get("events", []):
        for segment in event.get("segs") or []:
            pieces.append(html.unescape(segment.get("utf8", "")))
    return "".join(pieces).strip()


def parse_vtt_subtitle(content: str) -> str:
    output = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit() or line.startswith(("Kind:", "Language:")):
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", line))
        if text and (not output or output[-1] != text):
            output.append(text)
    return "\n".join(output)


def parse_srt_subtitle(content: str) -> str:
    return parse_vtt_subtitle(content)


def download_and_parse_subtitle(subtitle_url: str, format_type: str = "json3") -> Optional[str]:
    response = requests.get(subtitle_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    if format_type == "json3":
        return parse_json3_subtitle(response.text)
    if format_type == "srt":
        return parse_srt_subtitle(response.text)
    return parse_vtt_subtitle(response.text)


def _valid_cookie_file(path: Optional[str]) -> bool:
    """Only opt-in cookies that look like a non-empty Netscape jar are used."""
    if not path:
        return False
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size > 100 and p.read_text(encoding="utf-8", errors="ignore").startswith("# Netscape HTTP Cookie File")
    except OSError:
        return False


def _extract_with_ytdlp(url: str, cookie_file: Optional[str]) -> Dict[str, Any]:
    options: Dict[str, Any] = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": False, "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": ["ja", "en"],
        "extractor_args": {"youtube": {"player_client": ["android_vr", "web_safari", "web"]}},
    }
    # Cookies are never forced merely because the repository's legacy file exists.
    if _valid_cookie_file(cookie_file):
        options["cookiefile"] = cookie_file
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def fetch_youtube_info(url: str, cookies_file: Optional[str] = None, send_message_func=None) -> Tuple[Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    canonical = canonical_youtube_url(url)
    try:
        try:
            info = _extract_with_ytdlp(canonical, cookies_file)
        except Exception:
            info = _watch_page_metadata(canonical)
        selected = select_preferred_subtitle(info.get("subtitles") or {}, info.get("automatic_captions") or {})
        transcript = None
        if selected:
            subtitle, language, is_auto = selected
            try:
                transcript = download_and_parse_subtitle(subtitle["url"], subtitle.get("ext", "json3"))
            except Exception:
                transcript = None
        if not transcript:
            video_id = extract_video_id(canonical)
            if not video_id:
                raise RuntimeError("動画IDがありません")
            transcript, language, is_auto = _public_transcript(video_id)
        if not transcript:
            raise RuntimeError("字幕データが空でした")
        if len(transcript) > MAX_TRANSCRIPT_CHARS:
            raise RuntimeError("字幕が処理上限を超えています")
        metadata = {
            "channel": info.get("uploader") or info.get("channel") or "",
            "channel_id": info.get("channel_id", ""), "duration": info.get("duration", 0),
            "view_count": info.get("view_count", 0), "like_count": info.get("like_count", 0),
            "upload_date": info.get("upload_date", ""), "tags": info.get("tags") or [],
            "categories": info.get("categories") or [], "thumbnail": info.get("thumbnail", ""),
            "video_id": extract_video_id(canonical), "url": canonical,
            "transcript_language": language, "transcript_is_auto": is_auto,
        }
        return info.get("title") or "", info.get("description") or "", transcript, metadata
    except Exception as exc:
        # Do not leak signed caption URLs, cookies, or extractor internals to Discord/logs.
        raise RuntimeError(f"YouTube動画または字幕の取得に失敗しました ({type(exc).__name__})") from None


def format_youtube_content(title: str, description: str, transcript: str, metadata: Dict[str, Any]) -> str:
    return f"## 動画情報\nタイトル: {title}\nチャンネル: {metadata.get('channel', '')}\n\n## 説明文\n{description}\n\n## 字幕\n{transcript}"
