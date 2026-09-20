"""
Basic configuration / environment loading.
"""
import os
import platform
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Keep configuration validation usable in minimal installs.
    def load_dotenv():
        return False

load_dotenv()

API_KEY = os.environ.get("GROQ_API_KEY")
API_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"

# Model used for the agent loop. Change as needed.
MODEL_NAME = os.environ.get("JARVIS_MODEL", DEFAULT_MODEL)

# Voice provider settings. These can be changed without editing Python code.
STT_MODEL = os.environ.get("JARVIS_STT_MODEL", "whisper-large-v3")
# ISO-639-1 language spoken to Jarvis. Multi-language detection/switching is
# out of scope for now; this should match the language actually being spoken.
STT_LANGUAGE = os.environ.get("JARVIS_STT_LANGUAGE", "en")
TTS_MODEL = os.environ.get("JARVIS_TTS_MODEL", "canopylabs/orpheus-v1-english")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "autumn")

# Orpheus English voices supported by Groq. Keep this list local so
# a typo is reported during startup instead of after the first voice request.
ORPHEUS_VALID_VOICES = frozenset(
    {
        "autumn",
        "diana",
        "hannah",
        "austin",
        "daniel",
        "troy",
    }
)

# openWakeWord model name, or a path to a custom model file trained later.
# Custom model files must be supplied deliberately; Jarvis never trains them.
JARVIS_WAKEWORD_MODEL = os.environ.get("JARVIS_WAKEWORD_MODEL", "hey_jarvis")
_wakeword_threshold_value = os.environ.get("JARVIS_WAKEWORD_THRESHOLD", "0.5")
try:
    JARVIS_WAKEWORD_THRESHOLD = float(_wakeword_threshold_value)
except (TypeError, ValueError):
    # Preserve the bad value for validate_config() to report clearly.
    JARVIS_WAKEWORD_THRESHOLD = _wakeword_threshold_value

OPENWAKEWORD_VALID_MODELS = frozenset(
    {"alexa", "hey_mycroft", "hey_jarvis", "hey_rhasspy", "timer", "weather"}
)

# Fixed application launch commands. Add new entries deliberately here; never
# accept arbitrary paths or commands from the model or from user input.
ALLOWED_APPS = {
    "notepad": {
        "Windows": ["notepad.exe"],
        "Darwin": ["open", "-a", "TextEdit"],
        "Linux": ["gedit"],
    },
    "calculator": {
        "Windows": ["calc.exe"],
        "Darwin": ["open", "-a", "Calculator"],
        "Linux": ["gnome-calculator"],
    },
    "file_explorer": {
        "Windows": ["explorer.exe"],
        "Darwin": ["open", "-a", "Finder"],
        "Linux": ["xdg-open", "."],
    },
}

PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", PROJECT_DIR / "downloads"))


class ConfigValidationError(RuntimeError):
    """Raised when one or more startup configuration checks fail."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__("Configuration validation failed:\n" + "\n".join(
            f"- {error}" for error in self.errors
        ))


def validate_config():
    """Validate all startup configuration and raise one aggregated error."""
    errors = []

    if not isinstance(API_KEY, str) or not API_KEY.strip():
        errors.append("GROQ_API_KEY must be present and non-empty.")

    if VOICE_ENABLED and TTS_VOICE not in ORPHEUS_VALID_VOICES:
        errors.append(
            f"JARVIS_TTS_VOICE '{TTS_VOICE}' is not a known Orpheus voice."
        )

    wakeword_model = JARVIS_WAKEWORD_MODEL
    if not isinstance(wakeword_model, str) or not wakeword_model.strip():
        errors.append("JARVIS_WAKEWORD_MODEL must be a shipped model name or an existing file path.")
    elif wakeword_model not in OPENWAKEWORD_VALID_MODELS and not Path(wakeword_model).is_file():
        errors.append(
            f"JARVIS_WAKEWORD_MODEL '{wakeword_model}' is not shipped by openWakeWord "
            "and is not an existing model file."
        )

    try:
        threshold = float(JARVIS_WAKEWORD_THRESHOLD)
        if not 0 <= threshold <= 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("JARVIS_WAKEWORD_THRESHOLD must be a float between 0 and 1.")

    system = platform.system()
    if not isinstance(ALLOWED_APPS, dict) or not ALLOWED_APPS:
        errors.append("ALLOWED_APPS must be a non-empty whitelist dictionary.")
    else:
        for app_name, platform_commands in ALLOWED_APPS.items():
            if not isinstance(app_name, str) or not app_name.strip():
                errors.append("ALLOWED_APPS contains an empty or malformed application name.")
                continue
            if not isinstance(platform_commands, dict):
                errors.append(f"ALLOWED_APPS entry '{app_name}' is malformed.")
                continue
            command = platform_commands.get(system)
            if not isinstance(command, (list, tuple)) or not command or any(
                not isinstance(part, str) or not part.strip() for part in command
            ):
                errors.append(
                    f"ALLOWED_APPS entry '{app_name}' has no valid command for {system}."
                )

    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not DOWNLOAD_DIR.is_dir():
            raise NotADirectoryError(str(DOWNLOAD_DIR))
        with tempfile.NamedTemporaryFile(dir=DOWNLOAD_DIR, prefix=".jarvis-config-") as probe:
            pass
    except (OSError, TypeError, ValueError) as error:
        errors.append(f"DOWNLOAD_DIR '{DOWNLOAD_DIR}' is not writable: {error}")

    if errors:
        raise ConfigValidationError(errors)


def _check_voice_dependencies() -> tuple[bool, str]:
    missing = []
    for module_name in ("numpy", "sounddevice", "soundfile"):
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)

    if missing:
        names = ", ".join(missing)
        return (
            False,
            f"Voice dependencies are unavailable ({names}). "
            "Install them with: .venv/bin/pip install -r requirements.txt",
        )
    return True, ""


# Checked at startup so /voice can fail cleanly without an audio traceback.
VOICE_ENABLED, VOICE_DEPENDENCY_ERROR = _check_voice_dependencies()

# Max characters of page text fed back to the model, to keep context small.
MAX_PAGE_TEXT_CHARS = 4000
