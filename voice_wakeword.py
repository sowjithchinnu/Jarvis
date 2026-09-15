"""Local-only wake-word detection for Jarvis.

This module keeps microphone audio on the local machine. Audio is passed only
to the local openWakeWord model and is never sent over the network or passed
to :mod:`voice_provider`. The default model is openWakeWord's pretrained
``hey_jarvis`` model, which detects the phrase "hey jarvis". Install the
standard model files once with::

    from openwakeword.utils import download_models
    download_models()

The wake-word callback is intentionally the only action this module performs;
it does not bypass or implement any confirmation flow.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from config import JARVIS_WAKEWORD_MODEL, JARVIS_WAKEWORD_THRESHOLD

logger = logging.getLogger(__name__)

SAMPLE_RATE: Final[int] = 16_000
CHANNELS: Final[int] = 1
FRAME_DURATION_SECONDS: Final[float] = 0.08
FRAME_SAMPLES: Final[int] = int(SAMPLE_RATE * FRAME_DURATION_SECONDS)
DEFAULT_WAKE_WORD: Final[str] = "hey jarvis"
DEFAULT_MODEL_NAME: Final[str] = JARVIS_WAKEWORD_MODEL
DEFAULT_THRESHOLD: Final[float] = JARVIS_WAKEWORD_THRESHOLD
DEFAULT_DETECTION_COOLDOWN_SECONDS: Final[float] = 2.0


class WakeWordListenerError(RuntimeError):
    """Raised when the wake-word model cannot be initialized at ``start()``."""


class WakeWordListener:
    """Listen for one local openWakeWord model on a dedicated background thread."""

    def __init__(
        self,
        callback: Callable[[], None],
        wake_word: str = DEFAULT_WAKE_WORD,
        threshold: float = DEFAULT_THRESHOLD,
        detection_cooldown_seconds: float = DEFAULT_DETECTION_COOLDOWN_SECONDS,
        error_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not callable(callback):
            raise TypeError("callback must be callable")
        if not isinstance(wake_word, str) or not wake_word.strip():
            raise ValueError("wake_word must be a non-empty string")
        if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if detection_cooldown_seconds < 0:
            raise ValueError("detection_cooldown_seconds must not be negative")

        normalized_wake_word = " ".join(wake_word.lower().split())
        if normalized_wake_word != DEFAULT_WAKE_WORD:
            raise ValueError(
                f"No bundled openWakeWord model is configured for '{wake_word}'. "
                f"Use '{DEFAULT_WAKE_WORD}'."
            )

        self._callback = callback
        self._error_callback = error_callback
        self._threshold = float(threshold)
        self._detection_cooldown_seconds = detection_cooldown_seconds
        self._model_name = DEFAULT_MODEL_NAME
        self._model: Any = None
        self._thread: threading.Thread | None = None
        self._stream: Any = None
        self._stop_event = threading.Event()
        self._state_lock = threading.RLock()
        self._last_detection_at = 0.0
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        """Return the most recent runtime error, if the listener stopped because of one."""
        with self._state_lock:
            return self._last_error

    def start(self) -> None:
        """Load the local model and start microphone listening.

        ``WakeWordListenerError`` is raised when openWakeWord or the selected
        model files are unavailable. Audio-device and inference failures after
        startup stop the listener and are available through ``last_error`` and
        ``error_callback`` when one was supplied.
        """
        with self._state_lock:
            existing_thread = self._thread
            stopping_existing_thread = (
                existing_thread is not None
                and existing_thread.is_alive()
                and self._stop_event.is_set()
            )
            if existing_thread is not None and existing_thread.is_alive() and not stopping_existing_thread:
                return
        if stopping_existing_thread and existing_thread is not threading.current_thread():
            existing_thread.join(timeout=2.0)
        if stopping_existing_thread and existing_thread.is_alive():
            raise WakeWordListenerError(
                "The previous wake-word listener thread has not stopped."
            )

        with self._state_lock:
            self._stop_event.clear()
            self._last_error = None
            self._last_detection_at = 0.0

        try:
            model = self._load_model()
        except Exception as error:
            message = (
                "Wake-word listener unavailable: openWakeWord or its "
                f"'{self._model_name}' model files could not be loaded ({error})."
            )
            self._report_error(message)
            raise WakeWordListenerError(message) from error

        with self._state_lock:
            self._model = model
            self._thread = threading.Thread(
                target=self._run,
                name="jarvis-wake-word",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop listening and release the microphone stream cleanly."""
        self._stop_event.set()
        with self._state_lock:
            stream = self._stream
            thread = self._thread

        if stream is not None:
            try:
                stream.stop()
            except Exception:
                logger.debug("Unable to stop wake-word audio stream", exc_info=True)

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

        with self._state_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = None
                self._stream = None
                self._model = None

    def _load_model(self) -> Any:
        try:
            import openwakeword
            from openwakeword import utils
            from openwakeword.model import Model
        except ImportError as error:
            raise RuntimeError(
                "openWakeWord is not installed; install it with "
                "'.venv/bin/pip install openwakeword'."
            ) from error

        model_path = Path(self._model_name)
        if model_path.suffix.lower() in {".onnx", ".tflite"} and not model_path.exists():
            raise RuntimeError(f"configured model file was not found: {self._model_name}")

        if not model_path.exists():
            # This downloads only the library's standard pretrained model set;
            # it never trains or uploads any audio or custom model.
            utils.download_models()

        return Model(wakeword_models=[self._model_name])

    def _run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
            ) as stream:
                with self._state_lock:
                    self._stream = stream

                rolling_audio = np.empty(0, dtype=np.int16)
                while not self._stop_event.is_set():
                    audio, _overflowed = stream.read(FRAME_SAMPLES)
                    samples = np.asarray(audio, dtype=np.int16).reshape(-1)
                    if samples.size == 0:
                        continue
                    rolling_audio = np.concatenate((rolling_audio, samples))

                    while rolling_audio.size >= FRAME_SAMPLES:
                        frame = rolling_audio[:FRAME_SAMPLES]
                        rolling_audio = rolling_audio[FRAME_SAMPLES:]
                        prediction = self._model.predict(frame)
                        if self._is_wake_word_prediction(prediction):
                            self._notify_detection()
        except Exception as error:
            if not self._stop_event.is_set():
                self._report_error(f"Wake-word listener stopped: {error}")
        finally:
            with self._state_lock:
                self._stream = None

    def _is_wake_word_prediction(self, prediction: Any) -> bool:
        if not isinstance(prediction, dict):
            return False

        scores = []
        for value in prediction.values():
            try:
                scores.append(float(value))
            except (TypeError, ValueError):
                continue
        return bool(scores) and max(scores) >= self._threshold

    def _notify_detection(self) -> None:
        now = time.monotonic()
        if now - self._last_detection_at < self._detection_cooldown_seconds:
            return
        self._last_detection_at = now
        try:
            self._callback()
        except Exception as error:
            self._report_error(f"Wake-word callback failed: {error}")
            self._stop_event.set()

    def _report_error(self, message: str) -> None:
        with self._state_lock:
            self._last_error = message
        logger.error(message)
        if self._error_callback is not None:
            try:
                self._error_callback(message)
            except Exception:
                logger.debug("Wake-word error callback failed", exc_info=True)
