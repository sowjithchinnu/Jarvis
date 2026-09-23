import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from os_executor import (
    MAX_FILE_READ_BYTES,
    MAX_FILE_READ_CHARS,
    OSExecutor,
)


class OSExecutorNotificationAndFileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "allowed"
        self.root.mkdir()
        self.executor = OSExecutor()
        self.allowed_roots = patch("os_executor.ALLOWED_FILE_ROOTS", [self.root])
        self.allowed_roots.start()

    def tearDown(self):
        self.allowed_roots.stop()
        self.temp_dir.cleanup()

    def test_send_notification_truncates_title_and_message(self):
        notification = Mock()
        title = "T" * 80
        message = "M" * 250

        with patch("os_executor.notification", notification):
            result = self.executor.send_notification(title, message)

        self.assertEqual(result, "Desktop notification sent.")
        notification.notify.assert_called_once_with(
            title="T" * 60,
            message="M" * 200,
        )

    def test_list_directory_reports_contents_and_missing_path(self):
        (self.root / "note.txt").write_text("hello", encoding="utf-8")
        (self.root / "nested").mkdir()

        result = self.executor.list_directory(str(self.root))

        self.assertIn("note.txt (file, 5 bytes)", result)
        self.assertIn("nested (folder)", result)
        missing = self.executor.list_directory(str(self.root / "missing"))
        self.assertIn("does not exist", missing)

    def test_read_text_file_reads_small_file_and_truncates_long_file(self):
        small = self.root / "small.txt"
        small.write_text("hello", encoding="utf-8")
        self.assertEqual(self.executor.read_text_file(str(small)), "hello")

        long_file = self.root / "long.txt"
        long_file.write_text("x" * (MAX_FILE_READ_CHARS + 100), encoding="utf-8")
        result = self.executor.read_text_file(str(long_file))
        self.assertTrue(result.startswith("x" * MAX_FILE_READ_CHARS))
        self.assertIn("Content truncated", result)

    def test_read_text_file_rejects_oversized_and_outside_paths(self):
        oversized = self.root / "large.txt"
        oversized.write_bytes(b"x" * (MAX_FILE_READ_BYTES + 1))
        self.assertIn("file too large to read", self.executor.read_text_file(str(oversized)))

        outside = Path(self.temp_dir.name) / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        self.assertIn("outside the allowed", self.executor.read_text_file(str(outside)))
        traversal = self.root / ".." / "outside.txt"
        self.assertIn("outside the allowed", self.executor.read_text_file(str(traversal)))

    def test_read_text_file_rejects_secret_file_extensions(self):
        for filename in (".env", "private.pem", "server.key", "identity.ppk"):
            with self.subTest(filename=filename):
                secret_file = self.root / filename
                secret_file.write_text("secret", encoding="utf-8")
                result = self.executor.read_text_file(str(secret_file))
                self.assertIn("sensitive credential file", result)


if __name__ == "__main__":
    unittest.main()
