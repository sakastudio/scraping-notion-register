import json
import unittest
from unittest.mock import patch

import get_site


DECK_URL = "https://speakerdeck.com/recruitengineers/example-deck?slide=2"
PLAYER_URL = "https://speakerdeck.com/player/0123456789abcdef0123456789abcdef"


def deck_html(parts=None):
    parts = parts or [
        {"@type": "CreativeWork", "position": 1, "text": "最初のスライド\n検索語アルファ\f"},
        {"@type": "CreativeWork", "position": 2, "text": "次のスライド\n検索語ベータ\f"},
    ]
    payload = {
        "@context": "https://schema.org",
        "@type": "PresentationDigitalDocument",
        "name": "テスト資料",
        "hasPart": parts,
    }
    return f"""
    <html><head><script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script></head>
    <body><div class="speakerdeck-embed" data-id="0123456789abcdef0123456789abcdef"></div></body></html>
    """


PLAYER_HTML = """
<div class="js-sd-slide" data-url="https://files.speakerdeck.com/presentations/0123456789abcdef0123456789abcdef/slide_0.jpg?1">
  <div class="sd-player-slides--text">player text 1</div>
</div>
<div class="js-sd-slide" data-url="https://files.speakerdeck.com/presentations/0123456789abcdef0123456789abcdef/slide_1.jpg?2">
  <div class="sd-player-slides--text">player text 2</div>
</div>
"""


class SpeakerDeckTests(unittest.TestCase):
    def test_recognizes_only_public_deck_urls(self):
        self.assertTrue(get_site.is_speakerdeck_url(DECK_URL))
        self.assertTrue(get_site.is_speakerdeck_url("https://www.speakerdeck.com/user/deck"))
        self.assertFalse(get_site.is_speakerdeck_url("https://speakerdeck.com.evil.example/user/deck"))
        self.assertFalse(get_site.is_speakerdeck_url("http://speakerdeck.com/user/deck"))
        self.assertFalse(get_site.is_speakerdeck_url("https://speakerdeck.com/player/abc"))
        self.assertFalse(get_site.is_speakerdeck_url("https://speakerdeck.com/user"))
        self.assertFalse(get_site.is_speakerdeck_url("https://speakerdeck.com/c/programming"))
        self.assertFalse(get_site.is_speakerdeck_url("https://speakerdeck.com/p/featured"))
        self.assertFalse(get_site.is_speakerdeck_url("https://speakerdeck.com/s/featured"))

    def test_builds_markdown_with_every_slide_image_and_searchable_text(self):
        title, markdown = get_site.parse_speakerdeck_html(DECK_URL, deck_html(), PLAYER_HTML)

        self.assertEqual(title, "テスト資料")
        self.assertEqual(sum(line.startswith("## Slide ") and not line.startswith("###") for line in markdown.splitlines()), 2)
        self.assertIn("![Slide 1](https://files.speakerdeck.com/", markdown)
        self.assertIn("slide_1.jpg?2", markdown)
        self.assertIn("検索語アルファ", markdown)
        self.assertIn("検索語ベータ", markdown)
        self.assertNotIn("\f", markdown)
        self.assertLess(markdown.index("slide_0.jpg"), markdown.index("検索語アルファ"))
        self.assertLess(markdown.index("検索語アルファ"), markdown.index("slide_1.jpg"))

    def test_uses_player_text_when_jsonld_slide_text_is_empty(self):
        parts = [
            {"@type": "CreativeWork", "position": 1, "text": ""},
            {"@type": "CreativeWork", "position": 2, "text": ""},
        ]
        _title, markdown = get_site.parse_speakerdeck_html(DECK_URL, deck_html(parts), PLAYER_HTML)
        self.assertIn("player text 1", markdown)
        self.assertIn("player text 2", markdown)

    def test_slide_text_cannot_inject_an_external_image_block(self):
        for separator in ("\n", "\r", "\u2028"):
            parts = [
                {"@type": "CreativeWork", "position": 1, "text": f"本文{separator}![beacon](https://attacker.example/track.png)"},
                {"@type": "CreativeWork", "position": 2, "text": "安全な本文"},
            ]
            _title, markdown = get_site.parse_speakerdeck_html(DECK_URL, deck_html(parts), PLAYER_HTML)
            self.assertNotIn("\n![beacon]", markdown)
            self.assertIn("\\![beacon]", markdown)

    def test_rejects_duplicate_jsonld_positions(self):
        parts = [
            {"@type": "CreativeWork", "position": 1, "text": "first"},
            {"@type": "CreativeWork", "position": 1, "text": "overwriting"},
            {"@type": "CreativeWork", "position": 2, "text": "second"},
        ]
        with self.assertRaisesRegex(ValueError, "重複"):
            get_site.parse_speakerdeck_html(DECK_URL, deck_html(parts), PLAYER_HTML)

    def test_rejects_non_contiguous_jsonld_positions(self):
        parts = [
            {"@type": "CreativeWork", "position": 2, "text": "one"},
            {"@type": "CreativeWork", "position": 3, "text": "two"},
        ]
        with self.assertRaisesRegex(ValueError, "position"):
            get_site.parse_speakerdeck_html(DECK_URL, deck_html(parts), PLAYER_HTML)

    def test_player_request_sends_public_deck_as_referer(self):
        with patch.object(get_site, "_fetch_speakerdeck_html", side_effect=[deck_html(), PLAYER_HTML]) as fetch:
            get_site.fetch_speakerdeck_to_markdown(DECK_URL)
        canonical = "https://speakerdeck.com/recruitengineers/example-deck"
        self.assertEqual(fetch.call_args_list[0].args, (canonical,))
        self.assertEqual(fetch.call_args_list[1].kwargs["referer"], canonical)

    def test_rejects_missing_or_untrusted_slide_images(self):
        bad_player = PLAYER_HTML.replace(
            "https://files.speakerdeck.com/presentations/0123456789abcdef0123456789abcdef/slide_1.jpg?2",
            "https://evil.example/slide_1.jpg",
        )
        with self.assertRaisesRegex(ValueError, "画像URL"):
            get_site.parse_speakerdeck_html(DECK_URL, deck_html(), bad_player)

    def test_rejects_slide_count_mismatch_instead_of_partial_save(self):
        with self.assertRaisesRegex(ValueError, "position"):
            get_site.parse_speakerdeck_html(DECK_URL, deck_html(), PLAYER_HTML.split('<div class="js-sd-slide"')[0] + '<div class="js-sd-slide" data-url="https://files.speakerdeck.com/presentations/0123456789abcdef0123456789abcdef/slide_0.jpg?1"></div>')

    def test_routes_speakerdeck_without_firecrawl(self):
        expected = ("Deck", "slides")
        with (
            patch.object(get_site, "fetch_speakerdeck_to_markdown", return_value=expected) as fetch_deck,
            patch.object(get_site, "Firecrawl") as firecrawl,
        ):
            result = get_site.fetch_and_convert_to_markdown(DECK_URL)
        self.assertEqual(result, expected)
        fetch_deck.assert_called_once_with(DECK_URL)
        firecrawl.assert_not_called()


if __name__ == "__main__":
    unittest.main()
