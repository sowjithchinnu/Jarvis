import unittest
from unittest.mock import Mock, patch

from os_executor import OSExecutor


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.executor = OSExecutor()

    def test_get_clipboard_returns_mocked_text(self):
        pyperclip = Mock()
        pyperclip.paste.return_value = "clipboard text"

        with patch("os_executor.pyperclip", pyperclip):
            result = self.executor.get_clipboard()

        self.assertEqual(result, "clipboard text")
        pyperclip.paste.assert_called_once_with()

    def test_get_clipboard_reports_non_text_content(self):
        pyperclip = Mock()
        pyperclip.paste.return_value = object()

        with patch("os_executor.pyperclip", pyperclip):
            result = self.executor.get_clipboard()

        self.assertEqual(result, "Clipboard does not contain text.")

    def test_get_clipboard_returns_error_when_paste_raises(self):
        pyperclip = Mock()
        pyperclip.paste.side_effect = RuntimeError("clipboard unavailable")

        with patch("os_executor.pyperclip", pyperclip):
            result = self.executor.get_clipboard()

        self.assertIn("Error reading clipboard:", result)

    def test_set_clipboard_copies_exact_text_and_truncates_confirmation(self):
        pyperclip = Mock()
        text = "x" * 150

        with patch("os_executor.pyperclip", pyperclip):
            result = self.executor.set_clipboard(text)

        pyperclip.copy.assert_called_once_with(text)
        self.assertIn("x" * 97 + "...", result)
        self.assertNotIn(text, result)

    def test_set_clipboard_returns_error_when_copy_raises(self):
        pyperclip = Mock()
        pyperclip.copy.side_effect = RuntimeError("clipboard unavailable")

        with patch("os_executor.pyperclip", pyperclip):
            result = self.executor.set_clipboard("clipboard text")

        self.assertIn("Error setting clipboard:", result)

    def test_both_functions_report_missing_pyperclip(self):
        with patch("os_executor.pyperclip", None):
            get_result = self.executor.get_clipboard()
            set_result = self.executor.set_clipboard("clipboard text")

        self.assertIn("clipboard support not installed", get_result)
        self.assertIn("clipboard support not installed", set_result)


if __name__ == "__main__":
    unittest.main()
