"""
Basic configuration / environment loading.
"""
import os

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GROQ_API_KEY")
API_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"

if not API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. Add it to the .env file before running Jarvis."
    )

# Model used for the agent loop. Change as needed.
MODEL_NAME = os.environ.get("JARVIS_MODEL", DEFAULT_MODEL)

# Voice provider settings. These can be changed without editing Python code.
STT_MODEL = os.environ.get("JARVIS_STT_MODEL", "whisper-large-v3")
TTS_MODEL = os.environ.get("JARVIS_TTS_MODEL", "playai-tts")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "Fritz-PlayAI")


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
