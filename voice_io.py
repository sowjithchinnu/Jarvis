"""Push-to-talk microphone recording and audio playback for Jarvis.

This module is intentionally push-to-talk only. Always-listening and
wake-word support are deliberately separate, future scope.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import wave
from pathlib import Path


SAMPLE_RATE = 16_000
CHANNELS = 1
CHUNK_SIZE = 1_024
SILENCE_THRESHOLD = 0.01
SILENCE_SECONDS = 1.5
TEMP_FILE_PREFIX = "jarvis_audio_"


def _is_owned_temporary_file(file_path: str) -> bool:
    """Return whether ``file_path`` is a temporary file created by this module."""
    try:
        path = Path(file_path).resolve()
        temp_dir = Path(tempfile.gettempdir()).resolve()
        return path.parent == temp_dir and path.name.startswith(TEMP_FILE_PREFIX)
    except (OSError, RuntimeError, TypeError):
        return False


def _remove_owned_temporary_file(file_path: str) -> None:
    if _is_owned_temporary_file(file_path):
        try:
            os.unlink(file_path)
        except FileNotFoundError:
            pass
        except OSError:
            # Cleanup is best effort and must not hide the playback result.
            pass


def cleanup_audio_file(file_path: str) -> None:
    """Remove a temporary audio file created by this module, if applicable."""
    _remove_owned_temporary_file(file_path)


def record_audio(max_seconds: int = 15) -> str:
    """Record microphone input and return the path to a temporary WAV file.

    Recording ends at ``max_seconds`` or after approximately 1.5 seconds of
    silence following detected speech, whichever comes first. Errors are
    returned as strings so callers never need to catch audio-device failures.
    """
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, int):
        return "Error recording audio: max_seconds must be a positive integer."
    if max_seconds <= 0:
        return "Error recording audio: max_seconds must be a positive integer."

    output_path: str | None = None
    try:
        # Imports are delayed so Jarvis can start and report a useful error if
        # optional audio dependencies have not been installed yet.
        import numpy as np
        import sounddevice as sd

        chunks = []
        speech_started = False
        silence_started_at: float | None = None
        deadline = time.monotonic() + max_seconds

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=CHUNK_SIZE,
        ) as stream:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                frame_count = max(1, min(CHUNK_SIZE, int(remaining * SAMPLE_RATE)))
                data, _overflowed = stream.read(frame_count)
                samples = np.asarray(data, dtype=np.float32)
                if samples.size == 0:
                    continue
                chunks.append(samples.reshape(-1, CHANNELS))

                rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
                if rms >= SILENCE_THRESHOLD:
                    speech_started = True
                    silence_started_at = None
                elif speech_started:
                    if silence_started_at is None:
                        silence_started_at = time.monotonic()
                    elif time.monotonic() - silence_started_at >= SILENCE_SECONDS:
                        break

        audio = np.concatenate(chunks, axis=0) if chunks else np.empty((0, CHANNELS))
        pcm_audio = np.clip(audio, -1.0, 1.0)
        pcm_audio = (pcm_audio * 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".wav",
            prefix=TEMP_FILE_PREFIX,
            delete=False,
        ) as temporary_file:
            output_path = temporary_file.name

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm_audio.tobytes())

        return output_path
    except Exception as error:
        if output_path:
            _remove_owned_temporary_file(output_path)
        return f"Error recording audio: {error}"


def play_audio(file_path: str, interrupt_event: threading.Event | None = None) -> str:
    """Play an audio file and block until playback finishes.

    Temporary WAV files produced by :func:`record_audio` are removed after
    playback. Caller-owned files are left untouched. When ``interrupt_event``
    is supplied, playback is stopped by the sounddevice callback when the
    event is set and ``"Playback interrupted"`` is returned.
    """
    try:
        if not isinstance(file_path, str) or not file_path.strip():
            return "Error playing audio: file_path must be a non-empty string."

        import sounddevice as sd
        import soundfile as sf

        if interrupt_event is None:
            audio, sample_rate = sf.read(file_path, dtype="float32", always_2d=False)
            sd.play(audio, sample_rate)
            sd.wait()
            return "Audio playback completed."

        if interrupt_event.is_set():
            return "Playback interrupted"

        import numpy as np

        audio, sample_rate = sf.read(file_path, dtype="float32", always_2d=True)
        if audio.size == 0:
            return "Error playing audio: the audio file is empty."

        audio = np.asarray(audio, dtype=np.float32)
        channels = audio.shape[1]
        position = 0
        interrupted = False
        playback_finished = threading.Event()

        def callback(outdata, frames, _time_info, _status):
            nonlocal position, interrupted
            if interrupt_event.is_set():
                interrupted = True
                outdata.fill(0)
                raise sd.CallbackStop

            end = min(position + frames, len(audio))
            count = end - position
            if count:
                outdata[:count] = audio[position:end]
                position = end
            if count < frames:
                outdata[count:].fill(0)
                raise sd.CallbackStop

        with sd.OutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            blocksize=max(1, int(sample_rate * 0.1)),
            callback=callback,
            finished_callback=playback_finished.set,
        ):
            playback_finished.wait()

        if interrupted:
            return "Playback interrupted"
        return "Audio playback completed."
    except Exception as error:
        return f"Error playing audio: {error}"
    finally:
        if isinstance(file_path, str):
            _remove_owned_temporary_file(file_path)
