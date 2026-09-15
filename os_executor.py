"""Small, whitelisted operating-system actions for Jarvis.

This module intentionally exposes only screenshots, clipboard, and
system-volume controls. Clipboard access reads and writes shared OS state and
should be treated as potentially sensitive, despite being LOW risk
operationally. This module is not general-purpose OS control and does not
simulate keyboard or mouse input.
"""

from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Final

from PIL import ImageGrab

try:
    import pyperclip
except ImportError:
    pyperclip = None

PROJECT_DIR: Final[Path] = Path(__file__).resolve().parent
SCREENSHOTS_DIR: Final[Path] = PROJECT_DIR / "screenshots"
VOLUME_RANGE: Final[range] = range(0, 101)
CLIPBOARD_NOT_INSTALLED: Final[str] = "Error: clipboard support not installed."


class OSExecutor:
    """Expose a small, cross-platform whitelist of OS actions."""

    def take_screenshot(self) -> str:
        """Save a desktop screenshot and return its local path."""
        try:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_path = SCREENSHOTS_DIR / f"screenshot_{timestamp}.png"
            image = ImageGrab.grab()
            image.save(screenshot_path, format="PNG")
            return str(screenshot_path)
        except Exception as error:
            return f"Error taking screenshot: {error}"

    def get_volume(self) -> int | str:
        """Return the current system output volume as an integer percentage."""
        try:
            system = platform.system()
            if system == "Darwin":
                return self._mac_get_volume()
            if system == "Windows":
                return self._windows_get_volume()
            if system == "Linux":
                return self._linux_get_volume()
            return f"Error: unsupported operating system '{system}'."
        except Exception as error:
            return f"Error reading system volume: {error}"

    def set_volume(self, level: int) -> str:
        """Set system output volume to an integer percentage from 0 through 100."""
        if isinstance(level, bool) or not isinstance(level, int):
            return "Error: volume level must be an integer from 0 to 100."
        if level not in VOLUME_RANGE:
            return "Error: volume level must be between 0 and 100."

        try:
            system = platform.system()
            if system == "Darwin":
                return self._mac_set_volume(level)
            if system == "Windows":
                return self._windows_set_volume(level)
            if system == "Linux":
                return self._linux_set_volume(level)
            return f"Error: unsupported operating system '{system}'."
        except Exception as error:
            return f"Error setting system volume: {error}"

    def get_clipboard(self) -> str:
        """Return the current text content of the system clipboard."""
        try:
            if pyperclip is None:
                return CLIPBOARD_NOT_INSTALLED
            clipboard = pyperclip.paste()
            if not isinstance(clipboard, str):
                return "Clipboard does not contain text."
            return clipboard
        except Exception as error:
            return f"Error reading clipboard: {error}"

    def set_clipboard(self, text: str) -> str:
        """Set the system clipboard to the supplied text."""
        if not isinstance(text, str):
            return "Error: clipboard text must be a string."

        try:
            if pyperclip is None:
                return CLIPBOARD_NOT_INSTALLED
            pyperclip.copy(text)
            preview = text if len(text) <= 100 else f"{text[:97]}..."
            return f"Clipboard set to: {preview}"
        except Exception as error:
            return f"Error setting clipboard: {error}"

    @staticmethod
    def _run_command(command: list[str]) -> str:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    @classmethod
    def _mac_get_volume(cls) -> int:
        output = cls._run_command(
            ["osascript", "-e", "output volume of (get volume settings)"]
        )
        return int(output)

    @classmethod
    def _mac_set_volume(cls, level: int) -> str:
        cls._run_command(["osascript", "-e", f"set volume output volume {level}"])
        return f"System volume set to {level}."

    @staticmethod
    def _windows_endpoint():
        from pycaw.pycaw import AudioUtilities

        device = AudioUtilities.GetSpeakers()
        return device.EndpointVolume

    @classmethod
    def _windows_get_volume(cls) -> int:
        scalar = cls._windows_endpoint().GetMasterVolumeLevelScalar()
        return round(scalar * 100)

    @classmethod
    def _windows_set_volume(cls, level: int) -> str:
        cls._windows_endpoint().SetMasterVolumeLevelScalar(level / 100, None)
        return f"System volume set to {level}."

    @classmethod
    def _linux_get_volume(cls) -> int:
        try:
            output = cls._run_command(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]) 
            match = re.search(r"/(\d+)%", output)
            if match:
                return int(match.group(1))
        except FileNotFoundError:
            pass

        output = cls._run_command(["amixer", "get", "Master"])
        match = re.search(r"\[(\d+)%\]", output)
        if not match:
            raise RuntimeError("Could not parse volume from pactl or amixer.")
        return int(match.group(1))

    @classmethod
    def _linux_set_volume(cls, level: int) -> str:
        try:
            cls._run_command(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
        except FileNotFoundError:
            cls._run_command(["amixer", "sset", "Master", f"{level}%"])
        return f"System volume set to {level}."
