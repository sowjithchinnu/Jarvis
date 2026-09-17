import threading
import unittest
from unittest.mock import Mock

from agent import Agent


class FakeBrowser:
    def __init__(self, alive_states):
        self.alive_states = iter(alive_states)
        self._element_map = {"el_1": object()}
        self._undo_stack = [{"type": "navigate", "url": "https://example.com"}]
        self.relaunch_called = 0
        self.tool = Mock(return_value="fresh result")

    def is_alive(self):
        return next(self.alive_states)

    def relaunch(self):
        self.relaunch_called += 1
        self._element_map.clear()
        self._undo_stack.clear()

    def read_page_text(self):
        return self.tool()


class SessionRecoveryTests(unittest.TestCase):
    def _agent(self, browser):
        agent = object.__new__(Agent)
        agent.browser = browser
        agent.browser_factory = None
        agent.os_executor = Mock()
        agent.on_status = Mock()
        agent._last_tool_name = None
        agent._last_page_text = None
        agent._audit = Mock()
        agent.cancel_event = threading.Event()
        return agent

    def test_relaunch_clears_state_and_retries_tool(self):
        browser = FakeBrowser([False, True])
        agent = self._agent(browser)

        result = agent._execute_tool("read_page_text", {})

        self.assertEqual(result, "fresh result")
        self.assertEqual(browser.relaunch_called, 1)
        browser.tool.assert_called_once_with()
        self.assertEqual(browser._element_map, {})
        self.assertEqual(browser._undo_stack, [])
        agent.on_status.assert_called_once()
        self.assertIn("re-navigate", agent.on_status.call_args.args[0])

    def test_second_alive_check_failure_returns_without_looping(self):
        browser = FakeBrowser([False, False])
        agent = self._agent(browser)

        result = agent._execute_tool("read_page_text", {})

        self.assertIn("could not run", result)
        self.assertEqual(browser.relaunch_called, 1)
        browser.tool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
