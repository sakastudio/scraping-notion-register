import importlib
import unittest


class UrlCooldownTests(unittest.TestCase):
    def load_bot_module(self):
        import discord_bot
        return importlib.reload(discord_bot)

    def test_same_host_waits_until_one_minute_has_elapsed(self):
        bot = self.load_bot_module()
        bot._url_last_processed_at.clear()
        sleeps = []
        current_time = [1000.0]

        def now():
            return current_time[0]

        def sleep(seconds):
            sleeps.append(seconds)
            current_time[0] += seconds

        bot.wait_for_url_cooldown("https://www.reddit.com/r/gamedev/comments/first/", now_fn=now, sleep_fn=sleep)
        current_time[0] += 26.0
        bot.wait_for_url_cooldown("https://old.reddit.com/r/gamedev/comments/second/", now_fn=now, sleep_fn=sleep)

        self.assertEqual(sleeps, [34.0])

    def test_different_hosts_do_not_wait(self):
        bot = self.load_bot_module()
        bot._url_last_processed_at.clear()
        sleeps = []
        current_time = [2000.0]

        def now():
            return current_time[0]

        def sleep(seconds):
            sleeps.append(seconds)
            current_time[0] += seconds

        bot.wait_for_url_cooldown("https://example.com/a", now_fn=now, sleep_fn=sleep)
        current_time[0] += 10.0
        bot.wait_for_url_cooldown("https://another.example/b", now_fn=now, sleep_fn=sleep)

        self.assertEqual(sleeps, [])

    def test_reddit_short_url_uses_same_cooldown_key_as_reddit(self):
        bot = self.load_bot_module()

        self.assertEqual(bot._url_cooldown_key("https://redd.it/1mvkdac"), "reddit.com")
        self.assertEqual(bot._url_cooldown_key("https://www.reddit.com/r/gamedev/comments/1mvkdac/"), "reddit.com")

    def test_wait_callback_runs_before_sleep(self):
        bot = self.load_bot_module()
        bot._url_last_processed_at.clear()
        events = []
        current_time = [3000.0]

        def now():
            return current_time[0]

        def sleep(seconds):
            events.append(("sleep", seconds))
            current_time[0] += seconds

        def before_sleep(seconds):
            events.append(("notify", seconds))

        bot.wait_for_url_cooldown("https://example.com/a", now_fn=now, sleep_fn=sleep, before_sleep_fn=before_sleep)
        current_time[0] += 10.0
        bot.wait_for_url_cooldown("https://example.com/b", now_fn=now, sleep_fn=sleep, before_sleep_fn=before_sleep)

        self.assertEqual(events, [("notify", 50.0), ("sleep", 50.0)])

    def test_invalid_cooldown_env_falls_back_to_default(self):
        bot = self.load_bot_module()

        self.assertEqual(bot._parse_url_cooldown_seconds("invalid"), 60.0)
        self.assertEqual(bot._parse_url_cooldown_seconds("nan"), 60.0)
        self.assertEqual(bot._parse_url_cooldown_seconds("-1"), 60.0)

    def test_gamediscover_newsletter_url_strips_tracking_query_for_registration(self):
        bot = self.load_bot_module()

        normalized = bot.normalize_registration_url(
            "https://newsletter.gamediscover.co/p/may-2026s-top-new-pc-and-console?"
            "utm_source=post-email-title&publication_id=14089&post_id=200690906"
            "&utm_campaign=email-post-title&isFreemail=false&r=17wycc"
            "&triedRedirect=true&utm_medium=email#comments"
        )

        self.assertEqual(
            normalized,
            "https://newsletter.gamediscover.co/p/may-2026s-top-new-pc-and-console",
        )

    def test_non_gamediscover_url_keeps_query_for_registration(self):
        bot = self.load_bot_module()

        self.assertEqual(
            bot.normalize_registration_url("https://example.com/path?keep=1#section"),
            "https://example.com/path?keep=1#section",
        )


if __name__ == "__main__":
    unittest.main()
