import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from voice_provider import synthesize_speech, transcribe_audio


class FakeAPIError(Exception):
    status_code = 400


class VoiceProviderTests(unittest.TestCase):
    def setUp(self):
        self.audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.audio_file.close()

    def tearDown(self):
        os.unlink(self.audio_file.name)

    def _client(self):
        client = Mock()
        client.audio.transcriptions.create = Mock()
        client.audio.speech.create = Mock()
        return client

    @patch("voice_provider._client")
    def test_transcribe_audio_returns_successful_response(self, get_client):
        client = self._client()
        client.audio.transcriptions.create.return_value = SimpleNamespace(
            text="What is the weather today?"
        )
        get_client.return_value = client

        result = transcribe_audio(self.audio_file.name)

        self.assertEqual(result, "What is the weather today?")
        client.audio.transcriptions.create.assert_called_once()

    @patch("voice_provider._client")
    def test_transcribe_audio_returns_error_for_api_failure(self, get_client):
        client = self._client()
        client.audio.transcriptions.create.side_effect = FakeAPIError("bad request")
        get_client.return_value = client

        result = transcribe_audio(self.audio_file.name)

        self.assertIn("Error transcribing audio:", result)
        self.assertIn("bad request", result)

    @patch("voice_provider._client")
    def test_transcribe_audio_returns_error_for_empty_or_malformed_response(
        self, get_client
    ):
        client = self._client()
        get_client.return_value = client

        for response in (SimpleNamespace(text=""), object()):
            with self.subTest(response=response):
                client.audio.transcriptions.create.return_value = response
                result = transcribe_audio(self.audio_file.name)
                self.assertIn("Error transcribing audio:", result)

    @patch("voice_provider._client")
    def test_synthesize_speech_saves_successful_response(self, get_client):
        client = self._client()
        response = Mock()

        def write_audio(path):
            with open(path, "wb") as output:
                output.write(b"fake wav data")

        response.write_to_file.side_effect = write_audio
        client.audio.speech.create.return_value = response
        get_client.return_value = client

        output_path = synthesize_speech("Hello from Jarvis")
        try:
            self.assertTrue(os.path.isfile(output_path))
            response.write_to_file.assert_called_once_with(output_path)
        finally:
            if isinstance(output_path, str) and os.path.isfile(output_path):
                os.unlink(output_path)

    @patch("voice_provider._client")
    def test_synthesize_speech_returns_error_for_api_failure(self, get_client):
        client = self._client()
        client.audio.speech.create.side_effect = FakeAPIError("quota exceeded")
        get_client.return_value = client

        result = synthesize_speech("Hello from Jarvis")

        self.assertIn("Error synthesizing speech:", result)
        self.assertIn("quota exceeded", result)

    @patch("voice_provider._client")
    def test_synthesize_speech_returns_error_for_malformed_response(self, get_client):
        client = self._client()
        client.audio.speech.create.return_value = object()
        get_client.return_value = client

        result = synthesize_speech("Hello from Jarvis")

        self.assertIn("Error synthesizing speech:", result)


if __name__ == "__main__":
    unittest.main()
