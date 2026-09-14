import unittest
import sys
from types import ModuleType
from unittest.mock import Mock, patch

from voice_io import play_audio, record_audio


class VoiceIOTests(unittest.TestCase):
    def test_record_audio_returns_error_when_audio_library_fails(self):
        numpy = ModuleType("numpy")
        sounddevice = ModuleType("sounddevice")
        sounddevice.InputStream = Mock(
            side_effect=RuntimeError("microphone unavailable")
        )
        with patch.dict(
            sys.modules, {"numpy": numpy, "sounddevice": sounddevice}
        ):
            result = record_audio()

        self.assertIsInstance(result, str)
        self.assertIn("Error recording audio:", result)
        self.assertIn("microphone unavailable", result)

    def test_play_audio_returns_error_when_audio_library_fails(self):
        sounddevice = ModuleType("sounddevice")
        sounddevice.play = Mock(side_effect=RuntimeError("speaker unavailable"))
        soundfile = ModuleType("soundfile")
        soundfile.read = Mock(return_value=([0.0], 16_000))
        with patch.dict(
            sys.modules,
            {"sounddevice": sounddevice, "soundfile": soundfile},
        ):
            result = play_audio("test-output.wav")

        self.assertIsInstance(result, str)
        self.assertIn("Error playing audio:", result)
        self.assertIn("speaker unavailable", result)


if __name__ == "__main__":
    unittest.main()
