import unittest

from agent import Agent
from browser_executor import BrowserExecutor


class AgentValidationTests(unittest.TestCase):
    def test_rejects_invalid_element_id(self):
        result = Agent._validate_tool_args("click_element", {"element_id": "button"})
        self.assertIn("Invalid element_id", result)

    def test_rejects_extra_arguments_for_no_argument_tool(self):
        result = Agent._validate_tool_args("read_page_text", {"extra": True})
        self.assertIn("does not accept arguments", result)

    def test_accepts_valid_fill_arguments(self):
        self.assertIsNone(
            Agent._validate_tool_args(
                "fill_field", {"element_id": "el_2", "value": "hello"}
            )
        )

    def test_accepts_valid_canvas_stroke(self):
        self.assertIsNone(
            Agent._validate_tool_args(
                "draw_on_canvas",
                {"canvas_id": "el_3", "points": "10,10;20,20"},
            )
        )

    def test_accepts_valid_color(self):
        self.assertIsNone(Agent._validate_tool_args("set_color", {"color": "#ff0000"}))

    def test_rejects_invalid_color(self):
        result = Agent._validate_tool_args("set_color", {"color": "ff0000"})
        self.assertIn("Invalid color", result)

    def test_draw_tool_is_medium_risk(self):
        from risk_tiers import MEDIUM, get_risk

        self.assertEqual(get_risk("draw_on_canvas"), MEDIUM)

    def test_accepts_undo_without_arguments(self):
        self.assertIsNone(Agent._validate_tool_args("undo_last_action", {}))

    def test_trims_history_at_user_message_boundary(self):
        agent = object.__new__(Agent)
        agent.messages = [{"role": "system", "content": "system"}]
        for index in range(30):
            agent.messages.extend(
                [
                    {"role": "user", "content": str(index)},
                    {"role": "assistant", "content": "reply"},
                ]
            )
        agent._trim_history()
        self.assertLessEqual(len(agent.messages), 40)
        self.assertEqual(agent.messages[0]["role"], "system")
        self.assertEqual(agent.messages[1]["role"], "user")


class BrowserValidationTests(unittest.TestCase):
    def test_blocks_local_and_non_http_urls(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "http://127.0.0.1"):
            with self.assertRaises(ValueError):
                BrowserExecutor._validate_url(url)

    def test_allows_public_https_url(self):
        BrowserExecutor._validate_url("https://www.python.org")

    def test_undo_stack_starts_empty(self):
        browser = object.__new__(BrowserExecutor)
        browser._undo_stack = []
        self.assertEqual(browser._undo_stack, [])


if __name__ == "__main__":
    unittest.main()