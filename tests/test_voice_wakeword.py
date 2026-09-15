import sys
import threading
import time
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

from voice_wakeword import WakeWordListener, WakeWordListenerError


class FakeArray:
    def __init__(self, values):
        self.values = list(values)

    @property
    def size(self):
        return len(self.values)

    def reshape(self, *_shape):
        return self

    def __getitem__(self, item):
        value = self.values[item]
        if isinstance(item, slice):
            return FakeArray(value)
        return value


class FakeInputStream:
    instances = []

    def __init__(self, **_kwargs):
        self.entered = threading.Event()
        self.exited = threading.Event()
        self.stop_called = False
        self.__class__.instances.append(self)

    def __enter__(self):
        self.entered.set()
        return self

    def __exit__(self, _exception_type, _exception, _traceback):
        self.exited.set()
        return False

    def read(self, frame_count):
        time.sleep(0.001)
        return [[0] for _ in range(frame_count)], False

    def stop(self):
        self.stop_called = True


def fake_audio_modules():
    numpy = ModuleType("numpy")
    numpy.int16 = object()
    numpy.empty = lambda _size, dtype=None: FakeArray([])
    numpy.asarray = lambda values, dtype=None: FakeArray(values)
    numpy.concatenate = lambda arrays: FakeArray(
        value for array in arrays for value in array.values
    )

    sounddevice = ModuleType("sounddevice")
    sounddevice.InputStream = FakeInputStream
    return numpy, sounddevice


class WakeWordListenerTests(unittest.TestCase):
    def setUp(self):
        FakeInputStream.instances.clear()

    def _modules_context(self):
        numpy, sounddevice = fake_audio_modules()
        return patch.dict(
            sys.modules,
            {"numpy": numpy, "sounddevice": sounddevice},
        )

    def test_start_and_stop_manage_background_stream_lifecycle(self):
        model = Mock()
        model.predict.return_value = {"hey_jarvis": 0.1}
        listener = WakeWordListener(lambda: None)

        with self._modules_context(), patch.object(
            listener, "_load_model", return_value=model
        ):
            listener.start()
            self.assertTrue(FakeInputStream.instances[0].entered.wait(1))
            self.assertIsNotNone(listener._thread)
            self.assertTrue(listener._thread.is_alive())

            listener.stop()

        stream = FakeInputStream.instances[0]
        self.assertTrue(stream.stop_called)
        self.assertTrue(stream.exited.is_set())
        self.assertIsNone(listener._thread)

    def test_callback_fires_above_threshold(self):
        detected = threading.Event()
        model = Mock()
        model.predict.return_value = {"hey_jarvis": 0.9}
        listener = WakeWordListener(detected.set, threshold=0.5)

        with self._modules_context(), patch.object(
            listener, "_load_model", return_value=model
        ):
            listener.start()
            self.assertTrue(detected.wait(1))
            listener.stop()

    def test_callback_does_not_fire_below_threshold(self):
        detected = threading.Event()
        model = Mock()
        model.predict.return_value = {"hey_jarvis": 0.4}
        listener = WakeWordListener(detected.set, threshold=0.5)

        with self._modules_context(), patch.object(
            listener, "_load_model", return_value=model
        ):
            listener.start()
            self.assertTrue(FakeInputStream.instances[0].entered.wait(1))
            self.assertFalse(detected.wait(0.05))
            listener.stop()

    def test_start_reports_model_initialization_error(self):
        listener = WakeWordListener(lambda: None)

        with patch.object(
            listener, "_load_model", side_effect=RuntimeError("model files missing")
        ):
            with self.assertRaisesRegex(
                WakeWordListenerError, "model files could not be loaded"
            ):
                listener.start()

        self.assertIsNone(listener._thread)
        self.assertIn("model files missing", listener.last_error)


if __name__ == "__main__":
    unittest.main()
