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

# Max characters of page text fed back to the model, to keep context small.
MAX_PAGE_TEXT_CHARS = 4000
