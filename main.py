"""Responsive terminal entry point for Jarvis."""

import logging
import queue
import threading

from agent import Agent, AgentCancelled
from browser_executor import BrowserExecutor
from config import VOICE_DEPENDENCY_ERROR, VOICE_ENABLED
from voice_io import cleanup_audio_file, play_audio, record_audio
from voice_provider import synthesize_speech, transcribe_audio

RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
VOICE_TASK = object()


def choose_browser():
    print(f"{CYAN}Choose your browser:{RESET}")
    print("1. Google Chrome")
    print("2. Brave Browser")
    print("q. Exit")
    while True:
        try:
            choice = input("Browser [1/2/q]: ").strip().lower()
        except EOFError:
            return None
        if choice == "1":
            return "chrome"
        if choice == "2":
            return "brave"
        if choice in {"q", "quit", "exit"}:
            return None
        print(f"{YELLOW}Please choose 1, 2, or q.{RESET}")


def choose_mode():
    print(f"{CYAN}What would you like Jarvis to use?{RESET}")
    print("1. Browser tasks")
    print("2. Desktop tasks")
    print("3. Both")
    print("q. Exit")
    while True:
        try:
            choice = input("Mode [1/2/3/q]: ").strip().lower()
        except EOFError:
            return None
        if choice == "1":
            return "browser"
        if choice == "2":
            return "desktop"
        if choice == "3":
            return "both"
        if choice in {"q", "quit", "exit"}:
            return None
        print(f"{YELLOW}Please choose 1, 2, 3, or q.{RESET}")


class TerminalSession:
    def __init__(self, mode, browser_name=None):
        self.mode = mode
        self.browser_name = browser_name
        self.tasks = queue.Queue()
        self.cancel_event = threading.Event()
        self.stop_event = threading.Event()
        self.confirmation = None
        self.confirmation_lock = threading.Lock()
        self.worker = threading.Thread(target=self._worker, daemon=True)

    def start(self):
        self.worker.start()

    def _show_status(self, text):
        print(f"{DIM}• {text}{RESET}")

    def _confirm(self, description, require_phrase=False):
        request = {
            "description": description,
            "require_phrase": require_phrase,
            "event": threading.Event(),
            "approved": False,
        }
        with self.confirmation_lock:
            self.confirmation = request
        if require_phrase:
            print(f"\n{YELLOW}Jarvis wants to:{RESET} {description}")
            print(f"{YELLOW}Type SUBMIT, or /cancel:{RESET}")
        else:
            print(f"\n{YELLOW}Jarvis wants to:{RESET} {description}")
            print(f"{YELLOW}Proceed? [y/N] (or /cancel):{RESET}")
        request["event"].wait()
        with self.confirmation_lock:
            if self.confirmation is request:
                self.confirmation = None
        return request["approved"] and not self.cancel_event.is_set()

    def _worker(self):
        browser = None
        agent = None
        try:
            if self.mode in {"browser", "both"}:
                browser = BrowserExecutor(browser_name=self.browser_name, headless=False)
            agent = Agent(
                browser,
                confirm_callback=self._confirm,
                on_status=self._show_status,
                cancel_event=self.cancel_event,
            )
            while not self.stop_event.is_set():
                task = self.tasks.get()
                if task is None:
                    break
                if task is VOICE_TASK:
                    self._run_voice_turn(agent)
                    self.cancel_event.clear()
                    continue
                if task == "undo":
                    try:
                        self._show_status("Running undo")
                        result = agent._execute_tool("undo_last_action", {})
                        print(f"{CYAN}Jarvis:{RESET} {result}\n")
                    except Exception:
                        logging.getLogger(__name__).exception("Undo failed")
                        print(f"{RED}Jarvis error:{RESET} Undo failed. See jarvis.log for details.\n")
                    continue
                try:
                    reply = agent.chat(task)
                    print(f"{CYAN}Jarvis:{RESET} {reply}\n")
                except AgentCancelled:
                    print(f"{YELLOW}Jarvis:{RESET} Request cancelled.\n")
                except Exception:
                    logging.getLogger(__name__).exception("Request failed")
                    print(f"{RED}Jarvis error:{RESET} The request failed. See jarvis.log for details.\n")
                finally:
                    self.cancel_event.clear()
        finally:
            if agent is not None:
                agent.close()
            elif browser is not None:
                browser.close()

    def _run_voice_turn(self, agent):
        recording_path = None
        try:
            if not VOICE_ENABLED:
                print(f"{RED}Jarvis error:{RESET} {VOICE_DEPENDENCY_ERROR}\n")
                return
            self._show_status("Listening... (recording)")
            recording_path = record_audio()
            if recording_path.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {recording_path}\n")
                return

            self._show_status("Transcribing...")
            transcript = transcribe_audio(recording_path)
            if transcript.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {transcript}\n")
                return

            print(f"{GREEN}You (voice):{RESET} {transcript}\n")
            reply = agent.chat(transcript)
            print(f"{CYAN}Jarvis:{RESET} {reply}\n")

            self._show_status("Generating spoken reply...")
            speech_path = synthesize_speech(reply)
            if speech_path.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {speech_path}\n")
                return

            playback_result = play_audio(speech_path)
            if playback_result.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {playback_result}\n")
        except AgentCancelled:
            print(f"{YELLOW}Jarvis:{RESET} Request cancelled.\n")
        except Exception:
            logging.getLogger(__name__).exception("Voice request failed")
            print(f"{RED}Jarvis error:{RESET} The voice request failed. See jarvis.log for details.\n")
        finally:
            if recording_path and not recording_path.startswith("Error"):
                cleanup_audio_file(recording_path)

    def submit(self, text):
        self.tasks.put(text)

    def submit_voice(self):
        self.tasks.put(VOICE_TASK)

    def cancel(self):
        self.cancel_event.set()
        with self.confirmation_lock:
            request = self.confirmation
        if request is not None:
            request["approved"] = False
            request["event"].set()

    def stop(self):
        self.cancel()
        self.stop_event.set()
        self.tasks.put(None)
        self.worker.join(timeout=25)


def main():
    logging.basicConfig(
        filename="jarvis.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    print(f"{CYAN}╭─ Jarvis ─────────────────────────────────╮{RESET}")
    print(f"{CYAN}│ Terminal Jarvis                          │{RESET}")
    print(f"{CYAN}│ /cancel stops the current request       │{RESET}")
    print(f"{CYAN}│ /voice records a one-shot voice request │{RESET}")
    print(f"{CYAN}│ /quit or /exit closes Jarvis            │{RESET}")
    print(f"{CYAN}╰─────────────────────────────────────────╯{RESET}\n")

    mode = choose_mode()
    if mode is None:
        print(f"{DIM}Goodbye.{RESET}")
        return
    browser_name = None
    if mode in {"browser", "both"}:
        browser_name = choose_browser()
        if browser_name is None:
            print(f"{DIM}Goodbye.{RESET}")
            return

    session = TerminalSession(mode, browser_name)
    session.start()
    try:
        while True:
            try:
                user_text = input(f"{GREEN}You:{RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue
            command = user_text.lower()
            if command in {"/quit", "/exit"}:
                break
            if command == "/cancel":
                session.cancel()
                print(f"{YELLOW}Jarvis:{RESET} Cancellation requested.\n")
                continue
            with session.confirmation_lock:
                confirmation = session.confirmation
            if confirmation is not None:
                # Voice input is for the request itself, not for authorizing
                # risky actions; confirmations remain terminal keyboard-only.
                if confirmation["require_phrase"]:
                    confirmation["approved"] = user_text == "SUBMIT"
                else:
                    confirmation["approved"] = command in {"y", "yes"}
                confirmation["event"].set()
                continue
            if command == "/voice":
                if not VOICE_ENABLED:
                    print(f"{RED}Jarvis error:{RESET} {VOICE_DEPENDENCY_ERROR}\n")
                else:
                    session.submit_voice()
            else:
                session.submit("undo" if command == "/undo" else user_text)
    finally:
        session.stop()
        print(f"{DIM}Browser closed. Goodbye.{RESET}")


if __name__ == "__main__":
    main()
