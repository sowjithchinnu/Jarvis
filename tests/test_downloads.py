import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from browser_executor import BrowserExecutor


class FakeDownload:
    def __init__(self, source_path, filename):
        self.source_path = Path(source_path)
        self.suggested_filename = filename
        self.cancelled = False
        self.deleted = False

    def failure(self):
        return None

    def path(self):
        return self.source_path

    def save_as(self, destination):
        Path(destination).write_bytes(self.source_path.read_bytes())

    def cancel(self):
        self.cancelled = True

    def delete(self):
        self.deleted = True


class DownloadTests(unittest.TestCase):
    def make_executor(self):
        executor = object.__new__(BrowserExecutor)
        executor._download_lock = threading.Lock()
        executor._download_results = {}
        executor._last_download = None
        executor._download_setup_error = None
        return executor

    def test_filename_collision_gets_numeric_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            existing = download_dir / "report.txt"
            existing.write_text("original")
            source = root / "source.txt"
            source.write_text("new content")
            download = FakeDownload(source, "report.txt")
            executor = self.make_executor()

            with patch("browser_executor.DOWNLOAD_DIR", download_dir):
                result = executor._save_download(download)

            saved = download_dir / "report_1.txt"
            self.assertTrue(saved.exists())
            self.assertEqual(saved.read_text(), "new content")
            self.assertEqual(existing.read_text(), "original")
            self.assertIn("report_1.txt", result)

    def test_download_over_maximum_size_is_rejected_and_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            source = root / "large.bin"
            source.write_bytes(b"12345")
            download = FakeDownload(source, "large.bin")
            executor = self.make_executor()

            with patch("browser_executor.DOWNLOAD_DIR", download_dir), patch(
                "browser_executor.MAX_DOWNLOAD_BYTES", 4
            ):
                result = executor._save_download(download)

            self.assertIn("exceeds the maximum allowed size", result)
            self.assertTrue(download.cancelled)
            self.assertTrue(download.deleted)
            self.assertEqual(list(download_dir.iterdir()), [])

    def test_last_download_info_before_and_after_download(self):
        executor = self.make_executor()
        self.assertEqual(
            executor.get_last_download_info(),
            "No download has occurred yet.",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = root / "downloads"
            download_dir.mkdir()
            source = root / "report.txt"
            source.write_bytes(b"downloaded")
            download = FakeDownload(source, "report.txt")

            with patch("browser_executor.DOWNLOAD_DIR", download_dir):
                executor._save_download(download)
                result = executor.get_last_download_info()

            self.assertIn("Filename: report.txt", result)
            self.assertIn("Saved path:", result)
            self.assertIn("Size: 10 B", result)


if __name__ == "__main__":
    unittest.main()
