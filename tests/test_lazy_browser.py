import threading
import unittest
from unittest.mock import Mock, patch

from agent import Agent


class FakeBrowser:
    def __init__(self):
        self.close = Mock()

    def is_alive(self):
        return True

    def search_web(self, query):
        return f"Results for {query}"

    def open_url(self, url):
        return f"Opened {url}"


class LazyBrowserTests(unittest.TestCase):
    def _make_agent(self):
        browser_factory = Mock(side_effect=FakeBrowser)
        os_executor = Mock()
        os_executor.get_system_status.return_value = "system status"
        with patch("agent.OpenAI"), patch("agent.list_facts", return_value="No facts remembered yet."):
            agent = Agent(
                None,
                confirm_callback=Mock(),
                browser_factory=browser_factory,
                os_executor=os_executor,
                cancel_event=threading.Event(),
            )
        return agent, browser_factory, os_executor

    def test_browser_is_lazy_and_reused(self):
        agent, browser_factory, os_executor = self._make_agent()

        os_executor.get_system_status.assert_not_called()
        self.assertIsNone(agent.browser)
        self.assertEqual(agent._execute_tool("get_system_status", {}), "system status")
        browser_factory.assert_not_called()

        self.assertEqual(agent._execute_tool("search_web", {"query": "Jarvis"}), "Results for Jarvis")
        browser_factory.assert_called_once_with()
        first_browser = agent.browser

        self.assertEqual(
            agent._execute_tool("open_url", {"url": "https://example.com"}),
            "Opened https://example.com",
        )
        self.assertIs(agent.browser, first_browser)
        browser_factory.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
