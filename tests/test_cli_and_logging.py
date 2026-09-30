import io
import logging
import os
import unittest

import config
from main import parse_cli_args, resolve_startup_config


class CliParsingTests(unittest.TestCase):
    def test_each_flag_is_applied(self):
        cases = (
            (["--browser", "brave"], {"browser": "brave"}),
            (["--no-voice"], {"voice_enabled": False}),
            (["--no-wakeword"], {"autostart_wakeword": False}),
            (["--log-level", "debug"], {"log_level": "debug"}),
        )
        for argv, expected in cases:
            with self.subTest(argv=argv):
                config = resolve_startup_config(parse_cli_args(argv))
                for key, value in expected.items():
                    self.assertEqual(config[key], value)

    def test_flags_can_be_combined(self):
        args = parse_cli_args(
            [
                "--browser",
                "brave",
                "--no-voice",
                "--no-wakeword",
                "--log-level",
                "error",
            ]
        )
        self.assertEqual(
            resolve_startup_config(args),
            {
                "browser": "brave",
                "voice_enabled": False,
                "autostart_wakeword": False,
                "log_level": "error",
            },
        )

    def test_no_flags_preserve_configured_defaults(self):
        startup_config = resolve_startup_config(parse_cli_args([]))
        expected_log_level = os.environ.get("JARVIS_LOG_LEVEL", "info").strip().lower() or "info"
        if expected_log_level not in {"debug", "info", "warning", "error"}:
            expected_log_level = "info"
        self.assertEqual(startup_config["browser"], config.JARVIS_DEFAULT_BROWSER)
        self.assertEqual(
            startup_config["autostart_wakeword"],
            config.JARVIS_AUTOSTART_WAKEWORD,
        )
        self.assertEqual(startup_config["log_level"], expected_log_level)


class LoggingLevelTests(unittest.TestCase):
    def test_configured_level_suppresses_lower_priority_messages(self):
        logger = logging.getLogger("cli-logging-test")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger.handlers = [handler]
        logger.propagate = False
        try:
            for level_name in ("debug", "info", "warning", "error"):
                with self.subTest(level=level_name):
                    stream.seek(0)
                    stream.truncate(0)
                    logger.setLevel(getattr(logging, level_name.upper()))
                    logger.debug("debug message")
                    logger.info("info message")
                    logger.warning("warning message")
                    logger.error("error message")
                    output = stream.getvalue()
                    threshold = getattr(logging, level_name.upper())
                    self.assertEqual("debug message" in output, threshold <= logging.DEBUG)
                    self.assertEqual("info message" in output, threshold <= logging.INFO)
                    self.assertEqual("warning message" in output, threshold <= logging.WARNING)
                    self.assertEqual("error message" in output, threshold <= logging.ERROR)
        finally:
            logger.handlers.clear()
            logger.propagate = True


if __name__ == "__main__":
    unittest.main()
