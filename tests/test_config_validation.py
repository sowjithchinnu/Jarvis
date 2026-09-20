import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class ConfigValidationTests(unittest.TestCase):
    def setUp(self):
        self.download_dir = Path(tempfile.mkdtemp())
        self.defaults = {
            "API_KEY": "test-key",
            "TTS_VOICE": "autumn",
            "VOICE_ENABLED": True,
            "JARVIS_WAKEWORD_MODEL": "hey_jarvis",
            "JARVIS_WAKEWORD_THRESHOLD": 0.5,
            "ALLOWED_APPS": config.ALLOWED_APPS,
            "DOWNLOAD_DIR": self.download_dir,
        }

    def _validate_with(self, **changes):
        values = {**self.defaults, **changes}
        with patch.multiple(config, **values):
            return config.validate_config()

    def test_valid_config_passes_with_no_errors(self):
        self.assertIsNone(self._validate_with())

    def test_missing_api_key_is_reported(self):
        with self.assertRaisesRegex(config.ConfigValidationError, "GROQ_API_KEY"):
            self._validate_with(API_KEY="")

    def test_invalid_tts_voice_is_reported(self):
        with self.assertRaisesRegex(config.ConfigValidationError, "JARVIS_TTS_VOICE"):
            self._validate_with(TTS_VOICE="not-a-playai-voice")

    def test_invalid_wakeword_model_is_reported(self):
        with self.assertRaisesRegex(config.ConfigValidationError, "JARVIS_WAKEWORD_MODEL"):
            self._validate_with(JARVIS_WAKEWORD_MODEL="missing_model")

    def test_invalid_threshold_is_reported(self):
        with self.assertRaisesRegex(config.ConfigValidationError, "JARVIS_WAKEWORD_THRESHOLD"):
            self._validate_with(JARVIS_WAKEWORD_THRESHOLD="not-a-float")

    def test_malformed_allowed_apps_is_reported(self):
        with self.assertRaisesRegex(config.ConfigValidationError, "ALLOWED_APPS"):
            self._validate_with(ALLOWED_APPS={"calculator": {}})

    def test_unwritable_download_dir_is_reported(self):
        with patch.object(config, "DOWNLOAD_DIR", self.download_dir / "file"):
            (self.download_dir / "file").write_text("not a directory")
            with self.assertRaisesRegex(config.ConfigValidationError, "DOWNLOAD_DIR"):
                config.validate_config()

    def test_invalid_values_are_all_in_one_error(self):
        with self.assertRaises(config.ConfigValidationError) as context:
            self._validate_with(
                API_KEY=" ",
                TTS_VOICE="invalid",
                JARVIS_WAKEWORD_MODEL="invalid-model",
                JARVIS_WAKEWORD_THRESHOLD="2",
                ALLOWED_APPS={"calculator": {}},
            )

        message = str(context.exception)
        for setting in (
            "GROQ_API_KEY",
            "JARVIS_TTS_VOICE",
            "JARVIS_WAKEWORD_MODEL",
            "JARVIS_WAKEWORD_THRESHOLD",
            "ALLOWED_APPS",
        ):
            self.assertIn(setting, message)


if __name__ == "__main__":
    unittest.main()
