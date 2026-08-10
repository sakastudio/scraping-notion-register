import unittest
from types import SimpleNamespace
from unittest.mock import patch

import get_site


class DirectHtmlFallbackTests(unittest.TestCase):
    def test_html_conversion_extracts_title_and_readable_body(self):
        html = """
        <html><head><title>Example Article</title><style>.x{}</style></head>
        <body><nav>menu</nav><main><h1>Heading</h1><p>Useful text.</p></main>
        <script>alert('ignore')</script></body></html>
        """

        title, markdown = get_site.convert_html_to_markdown(
            html,
            "https://example.com/article",
        )

        self.assertEqual(title, "Example Article")
        self.assertIn("# Heading", markdown)
        self.assertIn("Useful text.", markdown)
        self.assertNotIn("alert", markdown)
        self.assertNotIn("menu", markdown)

    def test_firecrawl_failure_uses_direct_public_html_fallback(self):
        expected = ("Fallback title", "Fallback body")
        with (
            patch.object(get_site, "FIRECRAWL_API_KEY", "test-key"),
            patch.object(get_site, "Firecrawl") as firecrawl_class,
            patch.object(
                get_site,
                "fetch_public_html_to_markdown",
                return_value=expected,
            ) as fallback,
        ):
            firecrawl_class.return_value.scrape.side_effect = RuntimeError("Firecrawl failed")

            result = get_site.fetch_and_convert_to_markdown("https://example.com/article")

        self.assertEqual(result, expected)
        fallback.assert_called_once_with("https://example.com/article")

    def test_direct_fetch_rejects_private_destination(self):
        with self.assertRaisesRegex(ValueError, "公開HTTP"):
            get_site.fetch_public_html_to_markdown("http://127.0.0.1/private")

    def test_direct_fetch_pins_validated_ip_and_tls_hostname(self):
        response = SimpleNamespace(
            status=200,
            headers={"Content-Type": "text/html; charset=utf-8", "Content-Length": "35"},
            stream=lambda **_kwargs: [b"<html><body>safe</body></html>"],
            release_conn=lambda: None,
        )
        pool = SimpleNamespace(request=lambda *_args, **_kwargs: response, close=lambda: None)
        with (
            patch.object(get_site, "_resolve_public_ip", return_value="93.184.216.34"),
            patch.object(get_site.urllib3, "HTTPSConnectionPool", return_value=pool) as pool_class,
        ):
            _title, markdown = get_site.fetch_public_html_to_markdown("https://example.com/article")

        self.assertIn("safe", markdown)
        pool_class.assert_called_once()
        args, kwargs = pool_class.call_args
        self.assertEqual(args[0], "93.184.216.34")
        self.assertEqual(kwargs["assert_hostname"], "example.com")
        self.assertEqual(kwargs["server_hostname"], "example.com")

    def test_fallback_failure_preserves_both_errors(self):
        with (
            patch.object(get_site, "FIRECRAWL_API_KEY", "test-key"),
            patch.object(get_site, "Firecrawl") as firecrawl_class,
            patch.object(
                get_site,
                "fetch_public_html_to_markdown",
                side_effect=ValueError("direct failed"),
            ),
        ):
            firecrawl_class.return_value.scrape.side_effect = RuntimeError("Firecrawl failed")
            with self.assertRaisesRegex(RuntimeError, "Firecrawl failed.*direct failed"):
                get_site.fetch_and_convert_to_markdown("https://example.com/article")

    def test_direct_fetch_checks_deadline_before_dns(self):
        with (
            patch.object(get_site.time, "monotonic", side_effect=[100.0, 121.0]),
            patch.object(get_site, "_resolve_public_ip") as resolver,
        ):
            with self.assertRaisesRegex(TimeoutError, "20秒"):
                get_site.fetch_public_html_to_markdown("https://example.com/article")
        resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
