import json
import tempfile
import unittest
from pathlib import Path


class UrlPreprocessorTests(unittest.TestCase):
    def test_speakerdeck_variants_use_one_canonical_registration_url(self):
        from url_preprocessor import preprocess_registration_url

        expected = "https://speakerdeck.com/user/deck"
        self.assertEqual(
            preprocess_registration_url("https://www.speakerdeck.com/user/deck/?slide=2#x"),
            expected,
        )
        self.assertEqual(
            preprocess_registration_url("https://speakerdeck.com/user/deck?slide=9"),
            expected,
        )

    def test_default_domain_list_strips_gamediscover_query_and_fragment(self):
        from url_preprocessor import preprocess_registration_url

        self.assertEqual(
            preprocess_registration_url(
                "https://newsletter.gamediscover.co/p/may-2026s-top-new-pc-and-console?"
                "utm_source=post-email-title&publication_id=14089&post_id=200690906"
                "&utm_campaign=email-post-title&isFreemail=false&r=17wycc"
                "&triedRedirect=true&utm_medium=email#comments"
            ),
            "https://newsletter.gamediscover.co/p/may-2026s-top-new-pc-and-console",
        )

    def test_non_listed_domain_keeps_query_and_fragment(self):
        from url_preprocessor import preprocess_registration_url

        self.assertEqual(
            preprocess_registration_url("https://example.com/path?keep=1#section"),
            "https://example.com/path?keep=1#section",
        )

    def test_domain_list_can_be_extended_without_code_changes(self):
        from url_preprocessor import load_url_preprocessing_rules, preprocess_registration_url

        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "url_preprocessing_rules.json"
            rules_path.write_text(
                json.dumps({"strip_query_and_fragment_hosts": ["example.com"]}),
                encoding="utf-8",
            )

            rules = load_url_preprocessing_rules(rules_path)

        self.assertEqual(
            preprocess_registration_url("https://example.com/path?tracking=1#frag", rules=rules),
            "https://example.com/path",
        )

    def test_rules_loader_normalizes_hosts_and_ignores_blank_entries(self):
        from url_preprocessor import load_url_preprocessing_rules

        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "url_preprocessing_rules.json"
            rules_path.write_text(
                json.dumps({"strip_query_and_fragment_hosts": [" Newsletter.GameDiscover.co ", ""]}),
                encoding="utf-8",
            )

            rules = load_url_preprocessing_rules(rules_path)

        self.assertEqual(rules.strip_query_and_fragment_hosts, frozenset({"newsletter.gamediscover.co"}))


if __name__ == "__main__":
    unittest.main()
