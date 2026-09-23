"""Small, whitelisted operating-system actions for Jarvis.

This module intentionally exposes only screenshots, clipboard, read-only file
inspection, system-volume controls, system status, and launches for explicitly
whitelisted applications.
Clipboard access reads and writes shared OS state and should be treated as
potentially sensitive, despite being LOW risk operationally. This module is
not general-purpose OS control and does not simulate keyboard or mouse input.
"""

from __future__ import annotations

import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Final

from PIL import ImageGrab
from config import ALLOWED_APPS, ALLOWED_FILE_ROOTS

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import screen_brightness_control
except ImportError:
    screen_brightness_control = None

try:
    from plyer import notification
except ImportError:
    notification = None

PROJECT_DIR: Final[Path] = Path(__file__).resolve().parent
SCREENSHOTS_DIR: Final[Path] = PROJECT_DIR / "screenshots"
VOLUME_RANGE: Final[range] = range(0, 101)
BRIGHTNESS_RANGE: Final[range] = range(0, 101)
CLIPBOARD_NOT_INSTALLED: Final[str] = "Error: clipboard support not installed."
PSUTIL_NOT_INSTALLED: Final[str] = "Error: system status support not installed."
BRIGHTNESS_NOT_SUPPORTED: Final[str] = (
    "Error: brightness control not supported on this display/OS."
)
NOTIFICATION_NOT_INSTALLED: Final[str] = "Error: desktop notification support not installed."
MAX_FILE_READ_BYTES: Final[int] = 2 * 1024 * 1024
MAX_FILE_READ_CHARS: Final[int] = 4000
SECRET_FILE_NAMES: Final[frozenset[str]] = frozenset(
    {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "credentials.json"}
)
SECRET_FILE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".env", ".pem", ".key", ".ppk", ".p12", ".pfx", ".crt", ".cer"}
)


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

    def send_notification(self, title: str, message: str) -> str:
        """Display a bounded cross-platform desktop notification."""
        if not isinstance(title, str) or not isinstance(message, str):
            return "Error sending notification: title and message must be strings."

        try:
            if notification is None:
                return NOTIFICATION_NOT_INSTALLED
            notification.notify(
                title=title[:60],
                message=message[:200],
            )
            return "Desktop notification sent."
        except Exception as error:
            return f"Error sending notification: {error}"

    def list_directory(self, path: str) -> str:
        """List an allowed directory without reading file contents."""
        try:
            directory, error = self._resolve_allowed_path(path)
            if error:
                return error
            if not directory.exists():
                return f"Error listing directory: path does not exist: {path}"
            if not directory.is_dir():
                return f"Error listing directory: path is not a directory: {path}"

            entries = []
            for entry in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
                if entry.is_dir():
                    entries.append(f"{entry.name} (folder)")
                elif entry.is_file():
                    entries.append(f"{entry.name} (file, {entry.stat().st_size} bytes)")
            if not entries:
                return "Directory is empty."
            return "\n".join(entries)
        except Exception as error:
            return f"Error listing directory: {error}"

    def read_text_file(self, path: str) -> str:
        """Read an allowed, non-sensitive text file with size limits."""
        try:
            file_path, error = self._resolve_allowed_path(path)
            if error:
                return error
            if self._is_secret_file(file_path):
                return f"Refusing to read sensitive credential file: {file_path.name}"
            if not file_path.exists():
                return f"Error reading file: path does not exist: {path}"
            if not file_path.is_file():
                return f"Error reading file: path is not a file: {path}"

            file_size = file_path.stat().st_size
            if file_size > MAX_FILE_READ_BYTES:
                return (
                    f"Error reading file: file too large to read "
                    f"(maximum {MAX_FILE_READ_BYTES} bytes)."
                )
            content = file_path.read_text(encoding="utf-8")
            if len(content) > MAX_FILE_READ_CHARS:
                return (
                    content[:MAX_FILE_READ_CHARS]
                    + f"\n\n[Content truncated to {MAX_FILE_READ_CHARS} characters.]"
                )
            return content
        except Exception as error:
            return f"Error reading file: {error}"

    @staticmethod
    def _is_secret_file(path: Path) -> bool:
        name = path.name.casefold()
        return (
            name in SECRET_FILE_NAMES
            or name.startswith(".env")
            or name.startswith(("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"))
            or any(
                name.endswith(suffix) for suffix in SECRET_FILE_SUFFIXES
            )
        )

    @staticmethod
    def _resolve_allowed_path(path: str) -> tuple[Path | None, str | None]:
        if not isinstance(path, str) or not path.strip():
            return None, "Error: file path must be a non-empty string."
        try:
            resolved = Path(path).expanduser().resolve()
            allowed_roots = [Path(root).expanduser().resolve() for root in ALLOWED_FILE_ROOTS]
            if not any(resolved == root or root in resolved.parents for root in allowed_roots):
                return None, "Error: file path is outside the allowed file directories."
            return resolved, None
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return None, f"Error resolving file path: {error}"

    def open_application(self, app_name: str) -> str:
        """Launch an application identified by a fixed whitelist key."""
        try:
            if not isinstance(app_name, str):
                return "Error: application name must be a string."

            allowed_names = ", ".join(sorted(ALLOWED_APPS))
            if app_name not in ALLOWED_APPS:
                return (
                    f"Error: application '{app_name}' is not allowed. "
                    f"Allowed applications: {allowed_names}."
                )

            system = platform.system()
            command = ALLOWED_APPS[app_name].get(system)
            if command is None:
                return f"Error: application '{app_name}' is not supported on {system}."

            subprocess.Popen(command, shell=False)
            return f"Application '{app_name}' launched."
        except Exception as error:
            return f"Error launching application '{app_name}': {error}"

    def get_battery_status(self) -> str:
        """Return the current battery percentage and charging state."""
        try:
            if psutil is None:
                return PSUTIL_NOT_INSTALLED

            battery = psutil.sensors_battery()
            if battery is None:
                return "No battery detected."

            charging_state = "charging" if battery.power_plugged else "not charging"
            return f"Battery: {battery.percent:.1f}% ({charging_state})."
        except Exception as error:
            return f"Error reading battery status: {error}"

    def get_system_status(self) -> str:
        """Return CPU, memory, and primary-drive disk status."""
        try:
            if psutil is None:
                return PSUTIL_NOT_INSTALLED

            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            primary_drive = Path.home().anchor or "/"
            available_disk_gb = psutil.disk_usage(primary_drive).free / (1024**3)
            return (
                f"CPU: {cpu_percent:.1f}% | Memory: {memory_percent:.1f}% | "
                f"Available disk: {available_disk_gb:.1f} GB."
            )
        except Exception as error:
            return f"Error reading system status: {error}"

    def get_brightness(self) -> int | str:
        """Return the current primary display brightness as a percentage."""
        try:
            if screen_brightness_control is None:
                return "Error: brightness control support not installed."

            brightness_values = screen_brightness_control.get_brightness()
            if isinstance(brightness_values, (list, tuple)):
                if not brightness_values:
                    return BRIGHTNESS_NOT_SUPPORTED
                brightness = brightness_values[0]
            else:
                brightness = brightness_values

            if isinstance(brightness, bool) or not isinstance(brightness, (int, float)):
                return BRIGHTNESS_NOT_SUPPORTED
            if brightness < 0 or brightness > 100:
                return BRIGHTNESS_NOT_SUPPORTED
            return int(brightness)
        except Exception:
            return BRIGHTNESS_NOT_SUPPORTED

    def set_brightness(self, level: int) -> str:
        """Set display brightness to an integer percentage from 0 through 100."""
        if isinstance(level, bool) or not isinstance(level, int):
            return "Error: brightness level must be an integer from 0 to 100."
        if level not in BRIGHTNESS_RANGE:
            return "Error: brightness level must be between 0 and 100."

        try:
            if screen_brightness_control is None:
                return "Error: brightness control support not installed."

            result = screen_brightness_control.set_brightness(level)
            if isinstance(result, (list, tuple)) and not result:
                return BRIGHTNESS_NOT_SUPPORTED
            return f"Screen brightness set to {level}."
        except Exception:
            return BRIGHTNESS_NOT_SUPPORTED

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
