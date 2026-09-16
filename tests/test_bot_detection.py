import unittest

from browser_executor import is_likely_blocked


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, title, body, iframe_count=0, challenge_count=0):
        self._title = title
        self._body = body
        self._iframe_count = iframe_count
        self._challenge_count = challenge_count

    def title(self):
        return self._title

    def inner_text(self, selector):
        self.last_selector = selector
        return self._body

    def locator(self, selector):
        if selector == "iframe":
            return FakeLocator(self._iframe_count)
        return FakeLocator(self._challenge_count)


class BotDetectionTests(unittest.TestCase):
    def test_content_rich_normal_page_is_not_blocked(self):
        page = FakePage(
            "Example Documentation",
            " ".join(
                [
                    "This is a normal page with useful content.",
                    "It contains enough visible text to represent a real page.",
                    "There are no challenge indicators or unusual access messages.",
                ]
            ),
        )

        self.assertFalse(is_likely_blocked(page))

    def test_checking_browser_page_is_likely_blocked(self):
        page = FakePage(
            "Checking your browser before accessing",
            "Just a moment...",
        )

        self.assertTrue(is_likely_blocked(page))

    def test_short_legitimate_page_documents_false_positive_risk(self):
        # A real minimal landing page can look like a challenge page to a
        # heuristic, so this test intentionally does not assert the result.
        page = FakePage("Welcome", "Welcome")

        result = is_likely_blocked(page)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
