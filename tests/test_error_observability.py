import asyncio
import io
import json
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch


class ErrorObservabilityTests(unittest.TestCase):
    def test_url_event_log_keeps_raw_and_normalized_url_as_structured_json(self):
        import discord_bot as bot

        stream = io.StringIO()
        bot.log_url_event(
            bot.UrlEvent.DETECTED,
            raw_url="https://example.com/article?utm=1",
            url="https://example.com/article",
            channel_id=123,
            message_id=456,
            stream=stream,
        )

        line = stream.getvalue().strip()
        prefix, payload = line.split(" ", 1)
        self.assertEqual(prefix, bot.URL_LOG_PREFIX)
        data = json.loads(payload)
        self.assertEqual(data["event"], "detected")
        self.assertEqual(data["raw_url"], "https://example.com/article?utm=1")
        self.assertEqual(data["url"], "https://example.com/article")
        self.assertEqual(data["channel_id"], "123")
        self.assertEqual(data["message_id"], "456")

    def test_discord_exception_message_always_contains_copyable_url(self):
        import discord_bot as bot

        message = bot.format_url_error_message(
            "処理中にエラーが発生しました",
            "https://example.com/path?keep=1#section",
            RuntimeError("Firecrawl failed"),
            location="get_site.py:194",
        )

        self.assertIn("❌ 処理中にエラーが発生しました: Firecrawl failed", message)
        self.assertIn("対象URL:\nhttps://example.com/path?keep=1#section", message)
        self.assertIn("発生箇所: get_site.py:194", message)

    def test_long_discord_exception_is_truncated_without_losing_url(self):
        import discord_bot as bot

        url = "https://example.com/important"
        message = bot.format_url_error_message(
            "処理中にエラーが発生しました",
            url,
            RuntimeError("x" * 5000),
        )

        self.assertLessEqual(len(message), 2000)
        self.assertIn(f"対象URL:\n{url}", message)

    def test_detected_url_is_logged_when_discord_message_is_received(self):
        import discord_bot as bot

        class FakeChannel:
            id = 123

            async def send(self, _message):
                return None

        message = SimpleNamespace(
            author=SimpleNamespace(bot=False),
            webhook_id=None,
            channel=FakeChannel(),
            content="https://example.com/article",
            id=456,
        )
        bot.WATCH_CHANNEL_IDS = ["123"]

        with patch.object(bot, "log_url_event") as log_event:
            asyncio.run(bot.on_message(message))

        log_event.assert_called_once_with(
            bot.UrlEvent.DETECTED,
            raw_url="https://example.com/article",
            url="https://example.com/article",
            channel_id=123,
            message_id=456,
        )
        bot.task_queue.get_nowait()

    def test_processing_exception_discord_notification_contains_task_url(self):
        import discord_bot as bot

        url = "https://example.com/failing-page"
        sent_messages = []
        task = {"url": url, "channel_id": 123, "message_id": 456, "type": "register"}

        cooldown_patch = (
            patch.object(bot, "wait_for_url_cooldown", return_value=0)
            if hasattr(bot, "wait_for_url_cooldown")
            else nullcontext()
        )
        with (
            cooldown_patch,
            patch.object(bot, "fetch_and_convert_to_markdown", side_effect=RuntimeError("scrape failed")),
            patch.object(bot, "send_discord_message", side_effect=lambda _channel, message: sent_messages.append(message)),
            patch.object(bot, "log_url_event"),
            patch.object(bot.traceback, "print_exception"),
        ):
            bot.process_register_task(task)

        self.assertEqual(len(sent_messages), 2)
        self.assertIn("scrape failed", sent_messages[-1])
        self.assertIn(f"対象URL:\n{url}", sent_messages[-1])


if __name__ == "__main__":
    unittest.main()
