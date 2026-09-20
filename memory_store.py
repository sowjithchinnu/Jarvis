"""Local, unencrypted memory for preferences and task context.

This store is intentionally local and unencrypted. ``remember_fact`` must not
be used for secrets or credentials; it is for preferences and task context,
not passwords.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path


logger = logging.getLogger(__name__)
MEMORY_PATH = Path(__file__).resolve().parent / "memory.json"
MAX_FACTS = 200
_LOCK = threading.RLock()


def _empty_store() -> dict:
    return {"facts": [], "macros": {}}


def _load_store() -> dict:
    """Load valid facts and macros, treating malformed data as an empty store."""
    try:
        with MEMORY_PATH.open("r", encoding="utf-8") as memory_file:
            data = json.load(memory_file)
        facts = data.get("facts") if isinstance(data, dict) else None
        if not isinstance(facts, list):
            raise ValueError("missing facts list")
        valid_facts = [
            fact
            for fact in facts
            if isinstance(fact, dict)
            and isinstance(fact.get("text"), str)
            and isinstance(fact.get("timestamp"), str)
        ]
        if len(valid_facts) != len(facts):
            raise ValueError("malformed fact entry")
        macros = data.get("macros", {})
        if not isinstance(macros, dict) or any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(request_text, str)
            for name, request_text in macros.items()
        ):
            raise ValueError("malformed macros section")
        return {"facts": valid_facts[-MAX_FACTS:], "macros": macros}
    except FileNotFoundError:
        return _empty_store()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        logger.warning(
            "Memory store at %s could not be loaded (%s); starting fresh.",
            MEMORY_PATH,
            error,
        )
        return _empty_store()


def _write_store(store: dict[str, list[dict[str, str]]]) -> None:
    """Atomically replace the memory file with the supplied JSON store."""
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=MEMORY_PATH.parent,
            prefix=f".{MEMORY_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump(store, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, MEMORY_PATH)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def remember_fact(text: str) -> str:
    """Remember a preference or piece of task context."""
    if not isinstance(text, str) or not text.strip():
        return "Please provide a non-empty fact to remember."

    fact = {
        "text": text.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        store = _load_store()
        store["facts"].append(fact)
        store["facts"] = store["facts"][-MAX_FACTS:]
        _write_store(store)
    return f"Remembered: {fact['text']}"


def list_facts() -> str:
    """Return all remembered facts in a human-readable numbered list."""
    with _LOCK:
        facts = _load_store()["facts"]
    if not facts:
        return "No facts remembered yet."
    return "\n".join(
        f"{index}. {fact['text']} ({fact['timestamp']})"
        for index, fact in enumerate(facts, start=1)
    )


def forget_fact(match_text: str) -> str:
    """Remove facts whose text contains ``match_text`` case-insensitively."""
    if not isinstance(match_text, str) or not match_text.strip():
        return "Please provide text to match when forgetting a fact."

    match = match_text.casefold()
    with _LOCK:
        store = _load_store()
        original_count = len(store["facts"])
        store["facts"] = [
            fact for fact in store["facts"] if match not in fact["text"].casefold()
        ]
        removed = original_count - len(store["facts"])
        if removed:
            _write_store(store)
    if not removed:
        return f"No matching fact found for '{match_text}'."
    return f"Forgot {removed} fact(s) matching '{match_text}'."


def clear_all_facts() -> str:
    """Remove all remembered facts."""
    with _LOCK:
        store = _load_store()
        cleared = len(store["facts"])
        if cleared:
            store["facts"] = []
            _write_store(store)
    return f"Cleared {cleared} remembered fact(s)."


def save_macro(name: str, request_text: str) -> str:
    """Save or overwrite a named request macro."""
    if not isinstance(name, str) or not name.strip():
        return "Please provide a non-empty macro name."
    if not isinstance(request_text, str) or not request_text.strip():
        return "Please provide a non-empty request for the macro."

    macro_name = name.strip()
    request = request_text.strip()
    with _LOCK:
        store = _load_store()
        overwritten = macro_name in store["macros"]
        store["macros"][macro_name] = request
        _write_store(store)
    if overwritten:
        return f"Overwrote macro '{macro_name}'."
    return f"Saved macro '{macro_name}'."


def list_macros() -> str:
    """Return macro names and short previews in a human-readable list."""
    with _LOCK:
        macros = dict(_load_store()["macros"])
    if not macros:
        return "No macros saved yet."
    lines = []
    for name, request_text in sorted(macros.items(), key=lambda item: item[0].casefold()):
        preview = " ".join(request_text.split())
        if len(preview) > 60:
            preview = preview[:57] + "..."
        lines.append(f"- {name}: {preview}")
    return "\n".join(lines)


def get_macro(name: str) -> str | None:
    """Return a saved macro request, or ``None`` when the name is unknown."""
    if not isinstance(name, str):
        return None
    with _LOCK:
        return _load_store()["macros"].get(name.strip())


def delete_macro(name: str) -> str:
    """Delete a named macro, reporting clearly when it does not exist."""
    if not isinstance(name, str) or not name.strip():
        return "Please provide a non-empty macro name."

    macro_name = name.strip()
    with _LOCK:
        store = _load_store()
        if macro_name not in store["macros"]:
            return f"No macro found named '{macro_name}'."
        del store["macros"][macro_name]
        _write_store(store)
    return f"Deleted macro '{macro_name}'."
