"""Groq transcription and text-to-speech providers for Jarvis.

Spoken and transcribed text can contain sensitive content. This module never
logs those values; it only logs operation-level failures and status messages.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from openai import OpenAI

from config import (
    API_BASE_URL,
    API_KEY,
    STT_MODEL,
    TTS_MODEL as CONFIG_TTS_MODEL,
    TTS_VOICE as CONFIG_TTS_VOICE,
)
from groq_retry import is_rate_limit_error, rate_limit_message, request_with_retry


logger = logging.getLogger(__name__)

# These default to environment-configured values in config.py. For a local,
# one-line override, change the aliases below.
TRANSCRIPTION_MODEL = STT_MODEL
TTS_MODEL = CONFIG_TTS_MODEL
TTS_VOICE = CONFIG_TTS_VOICE
AUDIO_REQUEST_TIMEOUT = 20
TEMP_FILE_PREFIX = "jarvis_audio_"


def _client() -> OpenAI:
    client_options = {"api_key": API_KEY}
    if API_BASE_URL:
        client_options["base_url"] = API_BASE_URL
    return OpenAI(**client_options)


def transcribe_audio(file_path: str) -> str:
    """Transcribe an audio file with Groq Whisper, returning text or an error."""
    if not isinstance(file_path, str) or not file_path.strip():
        return "Error transcribing audio: file_path must be a non-empty string."
    if not Path(file_path).is_file():
        return f"Error transcribing audio: file not found: {file_path}"

    try:
        client = _client()
        response = request_with_retry(
            lambda: client.audio.transcriptions.create(
                model=TRANSCRIPTION_MODEL,
                file=Path(file_path),
                timeout=AUDIO_REQUEST_TIMEOUT,
            ),
            logger=logger,
            operation="Audio transcription request",
            log_error_details=False,
        )
        text = (getattr(response, "text", "") or "").strip()
        if not text:
            return "Error transcribing audio: the provider returned empty text."
        # Deliberately do not log the transcript, even at INFO or WARNING.
        logger.info("Audio transcription completed.")
        return text
    except Exception as error:
        if is_rate_limit_error(error):
            return f"Error transcribing audio: {rate_limit_message(error)}"
        if _is_timeout_error(error):
            return "Error transcribing audio: the request timed out."
        return f"Error transcribing audio: {error}"


def synthesize_speech(text: str) -> str:
    """Synthesize speech with Groq PlayAI and return a temporary audio path."""
    if not isinstance(text, str) or not text.strip():
        return "Error synthesizing speech: text must be a non-empty string."

    output_path: str | None = None
    try:
        client = _client()
        response = request_with_retry(
            lambda: client.audio.speech.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=text,
                response_format="wav",
                timeout=AUDIO_REQUEST_TIMEOUT,
            ),
            logger=logger,
            operation="Speech synthesis request",
            log_error_details=False,
        )

        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".wav",
            prefix=TEMP_FILE_PREFIX,
            delete=False,
        ) as temporary_file:
            output_path = temporary_file.name
        response.write_to_file(output_path)

        # Deliberately do not log the spoken text.
        logger.info("Speech synthesis completed.")
        return output_path
    except Exception as error:
        if output_path:
            _remove_file(output_path)
        if is_rate_limit_error(error):
            return f"Error synthesizing speech: {rate_limit_message(error)}"
        if _is_timeout_error(error):
            return "Error synthesizing speech: the request timed out."
        return f"Error synthesizing speech: {error}"


def _is_timeout_error(error: Exception) -> bool:
    error_name = type(error).__name__.lower()
    return (
        isinstance(error, TimeoutError)
        or "timeout" in error_name
        or "timed out" in str(error).lower()
    )


def _remove_file(file_path: str) -> None:
    """Best-effort cleanup for a partially written synthesis file."""
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        pass
