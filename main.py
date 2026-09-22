"""Responsive terminal entry point for Jarvis."""

import logging
import queue
import sys
import threading

from config import ConfigValidationError, validate_config
from memory_store import (
    clear_all_facts,
    delete_macro,
    forget_fact,
    get_macro,
    list_facts,
    list_macros,
    save_macro,
)

RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
VOICE_TASK = object()
WAKE_TRANSCRIPT_TASK = "wake_transcript"
WAKE_RESTART_TASK = "wake_restart"

HELP_TEXT = """Available commands:
/c, /cancel                 stop the current request
/v, /voice                  one-shot voice request
/vs /voice-set <name>       switch the active TTS voice
/vl /voice-list             list available TTS voices
/w on|off, /wake-on|/wake-off|/wakeword-on|/wakeword-off   toggle wake-word listening (on by default)
/mem|/memory list|forget|clear   manage remembered facts
/mac|/macro save|run|list|delete   manage request macros
/undo                       undo the last reversible browser action
/? /h /help                 show this help
/q, /quit, /exit            close Jarvis"""


class TerminalSession:
    def __init__(self, browser_name):
        self.browser_name = browser_name
        self._browser = None
        self.tasks = queue.Queue()
        self.cancel_event = threading.Event()
        self.stop_event = threading.Event()
        self.confirmation = None
        self.confirmation_lock = threading.Lock()
        self.wake_listener = None
        self.wake_lock = threading.Lock()
        self.wake_enabled = False
        self.wake_playback_interrupt = None
        self.wake_response_playing = False
        self.worker = threading.Thread(target=self._worker, daemon=True)

    def start(self):
        self.worker.start()

    def _show_status(self, text):
        print(f"{DIM}• {text}{RESET}")

    def _get_browser(self):
        if self._browser is None:
            browser_label = self.browser_name.title()
            print(f"{DIM}Launching {browser_label} for browser tasks...{RESET}")
            self._browser = BrowserExecutor(
                browser_name=self.browser_name,
                headless=False,
            )
        return self._browser

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
        agent = None
        try:
            agent = Agent(
                None,
                confirm_callback=self._confirm,
                on_status=self._show_status,
                browser_factory=self._get_browser,
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
                if isinstance(task, tuple) and task[0] == WAKE_TRANSCRIPT_TASK:
                    self._run_voice_transcript(agent, task[1], wake_triggered=True)
                    self.cancel_event.clear()
                    self._restart_wake_listener()
                    continue
                if isinstance(task, tuple) and task[0] == WAKE_RESTART_TASK:
                    self._restart_wake_listener()
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
            elif self._browser is not None:
                self._browser.close()

    def _run_voice_turn(self, agent):
        recording_path = None
        try:
            if not VOICE_ENABLED:
                print(f"{RED}Jarvis error:{RESET} {VOICE_DEPENDENCY_ERROR}\n")
                return
            self._show_status("Listening... (recording)")
            recording_path = record_audio()
            if recording_path == NO_SPEECH_MESSAGE:
                print(f"{YELLOW}{NO_SPEECH_MESSAGE}{RESET}\n")
                return
            if recording_path.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {recording_path}\n")
                return

            self._show_status("Transcribing...")
            transcript = transcribe_audio(recording_path)
            if transcript.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {transcript}\n")
                return

            print(f"{GREEN}You (voice):{RESET} {transcript}\n")
            self._run_voice_transcript(agent, transcript)
        except AgentCancelled:
            print(f"{YELLOW}Jarvis:{RESET} Request cancelled.\n")
        except Exception:
            logging.getLogger(__name__).exception("Voice request failed")
            print(f"{RED}Jarvis error:{RESET} The voice request failed. See jarvis.log for details.\n")
        finally:
            if recording_path and not recording_path.startswith("Error"):
                cleanup_audio_file(recording_path)

    def _run_voice_transcript(self, agent, transcript, wake_triggered=False):
        try:
            reply = agent.chat(transcript)
            print(f"{CYAN}Jarvis:{RESET} {reply}\n")

            self._show_status("Generating spoken reply...")
            speech_path = synthesize_speech(reply)
            if speech_path.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {speech_path}\n")
                return

            with self.wake_lock:
                interrupt_event = (
                    self.wake_playback_interrupt if self.wake_enabled else None
                )
                if interrupt_event is not None:
                    # This event interrupts audio playback only; it does not
                    # cancel an in-flight agent/tool operation. /cancel is
                    # deliberately the separate mechanism for that.
                    # Clear stale state before beginning the next response.
                    interrupt_event.clear()
                    self.wake_response_playing = True
            if wake_triggered:
                self._restart_wake_listener()
            try:
                playback_result = play_audio(
                    speech_path,
                    interrupt_event=interrupt_event,
                )
            finally:
                with self.wake_lock:
                    self.wake_response_playing = False
            if playback_result.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {playback_result}\n")
            elif playback_result == "Playback interrupted":
                print(f"{YELLOW}Jarvis:{RESET} Playback interrupted.\n")
        except AgentCancelled:
            print(f"{YELLOW}Jarvis:{RESET} Request cancelled.\n")
        except Exception:
            logging.getLogger(__name__).exception("Voice request failed")
            print(f"{RED}Jarvis error:{RESET} The voice request failed. See jarvis.log for details.\n")

    def _wake_word_detected(self):
        """Capture a follow-up utterance and enqueue it for the single worker."""
        with self.wake_lock:
            if self.wake_response_playing and self.wake_playback_interrupt is not None:
                self.wake_playback_interrupt.set()
                print("🎤 Wake word detected, interrupting playback...")
                return
        print("🎤 Wake word detected, listening...", flush=True)
        with self.wake_lock:
            listener = self.wake_listener
        if listener is not None:
            listener.stop()

        recording_path = None
        try:
            if not VOICE_ENABLED:
                print(f"{RED}Jarvis error:{RESET} {VOICE_DEPENDENCY_ERROR}\n")
                self.tasks.put((WAKE_RESTART_TASK, None))
                return

            recording_path = record_audio()
            if recording_path == NO_SPEECH_MESSAGE:
                print(f"{YELLOW}{NO_SPEECH_MESSAGE}{RESET}\n")
                self.tasks.put((WAKE_RESTART_TASK, None))
                return
            if recording_path.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {recording_path}\n")
                self.tasks.put((WAKE_RESTART_TASK, None))
                return

            transcript = transcribe_audio(recording_path)
            if transcript.startswith("Error"):
                print(f"{RED}Jarvis error:{RESET} {transcript}\n")
                self.tasks.put((WAKE_RESTART_TASK, None))
                return

            print(f"{GREEN}You (voice):{RESET} {transcript}\n")
            # Do not call agent.chat() here. Wake-word requests must share the
            # existing worker queue so they cannot run alongside typed input.
            self.tasks.put((WAKE_TRANSCRIPT_TASK, transcript))
        except Exception:
            logging.getLogger(__name__).exception("Wake-word follow-up failed")
            print(f"{RED}Jarvis error:{RESET} The wake-word request failed. See jarvis.log for details.\n")
            self.tasks.put((WAKE_RESTART_TASK, None))
        finally:
            if recording_path and not recording_path.startswith("Error"):
                cleanup_audio_file(recording_path)

    def _wake_word_error(self, message):
        print(f"{RED}Jarvis error:{RESET} {message}\n")

    def enable_wake_word(self):
        with self.wake_lock:
            if self.wake_listener is not None and self.wake_enabled:
                print(f"{YELLOW}Jarvis:{RESET} Wake-word listening is already active.\n")
                return
            listener = WakeWordListener(
                self._wake_word_detected,
                error_callback=self._wake_word_error,
            )
            self.wake_listener = listener
            self.wake_enabled = True
            self.wake_playback_interrupt = threading.Event()
        try:
            listener.start()
            print(f"{GREEN}🎤 Listening for 'Hey Jarvis'...{RESET}\n")
        except WakeWordListenerError:
            with self.wake_lock:
                self.wake_enabled = False
                self.wake_listener = None
                self.wake_playback_interrupt = None

    def disable_wake_word(self, announce=True):
        with self.wake_lock:
            listener = self.wake_listener
            was_enabled = self.wake_enabled
            self.wake_enabled = False
            self.wake_listener = None
            self.wake_playback_interrupt = None
            self.wake_response_playing = False
        if not was_enabled or listener is None:
            if announce:
                print(f"{YELLOW}Jarvis:{RESET} Wake-word listening is not active.\n")
            return
        listener.stop()
        if announce:
            print(f"{GREEN}Jarvis:{RESET} Wake-word listening disabled.\n")

    def _restart_wake_listener(self):
        with self.wake_lock:
            listener = self.wake_listener
            enabled = self.wake_enabled
        if not enabled or listener is None:
            return
        try:
            listener.start()
        except WakeWordListenerError as error:
            self._wake_word_error(str(error))

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
        self.disable_wake_word(announce=False)
        self.cancel()
        self.stop_event.set()
        self.tasks.put(None)
        self.worker.join(timeout=25)


def main():
    try:
        validate_config()
    except ConfigValidationError as error:
        print(f"{RED}{error}{RESET}", file=sys.stderr)
        raise SystemExit(1)

    # Delay optional/heavy application imports until configuration is known to
    # be usable, so invalid startup state is reported as configuration errors.
    global Agent, AgentCancelled, BrowserExecutor, JARVIS_DEFAULT_BROWSER
    global JARVIS_AUTOSTART_WAKEWORD
    global VOICE_DEPENDENCY_ERROR, VOICE_ENABLED
    global cleanup_audio_file, play_audio, record_audio, NO_SPEECH_MESSAGE
    global synthesize_speech, transcribe_audio, set_tts_voice, get_tts_voice
    global VALID_TTS_VOICES
    global WakeWordListener, WakeWordListenerError
    from agent import Agent, AgentCancelled
    from browser_executor import BrowserExecutor
    from config import (
        JARVIS_AUTOSTART_WAKEWORD,
        JARVIS_DEFAULT_BROWSER,
        VOICE_DEPENDENCY_ERROR,
        VOICE_ENABLED,
    )
    from voice_io import NO_SPEECH_MESSAGE, cleanup_audio_file, play_audio, record_audio
    from voice_provider import (
        VALID_TTS_VOICES,
        get_tts_voice,
        set_tts_voice,
        synthesize_speech,
        transcribe_audio,
    )
    from voice_wakeword import WakeWordListener, WakeWordListenerError

    logging.basicConfig(
        filename="jarvis.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    print("Type /help for commands.\n")

    session = TerminalSession(JARVIS_DEFAULT_BROWSER)
    session.start()
    if JARVIS_AUTOSTART_WAKEWORD:
        session.enable_wake_word()
    last_typed_request = None
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
            if command in {"/q", "/quit", "/exit"}:
                break
            if command in {"/?", "/h", "/help"}:
                print(f"{DIM}{HELP_TEXT}{RESET}\n")
                continue
            if command in {"/c", "/cancel"}:
                session.cancel()
                print(f"{YELLOW}Jarvis:{RESET} Cancellation requested.\n")
                continue
            if command in {"/w on", "/wake-on", "/wakeword-on"}:
                session.enable_wake_word()
                continue
            if command in {"/w off", "/wake-off", "/wakeword-off"}:
                session.disable_wake_word()
                continue
            if command in {"/vl", "/voice-list"}:
                print("Available voices:")
                for voice in VALID_TTS_VOICES:
                    marker = " (active)" if voice == get_tts_voice() else ""
                    print(f"- {voice}{marker}")
                print()
                continue
            if command == "/vs" or command.startswith("/vs ") or command == "/voice-set" or command.startswith("/voice-set "):
                voice_parts = user_text.split(maxsplit=1)
                if len(voice_parts) != 2 or not voice_parts[1].strip():
                    print(f"{YELLOW}Usage:{RESET} /voice-set <name>\n")
                else:
                    voice_name = voice_parts[1].strip().lower()
                    try:
                        set_tts_voice(voice_name)
                        print(f"{DIM}Active TTS voice: {voice_name}.{RESET}\n")
                    except ValueError as error:
                        print(f"{YELLOW}{error}{RESET}\n")
                continue
            with session.confirmation_lock:
                confirmation = session.confirmation
            if confirmation is not None:
                # Intentional: wake-word turns use this same keyboard-only
                # confirmation flow; spoken confirmation must not bypass it.
                # Voice input is for the request itself, not for authorizing
                # risky actions; confirmations remain terminal keyboard-only.
                if confirmation["require_phrase"]:
                    confirmation["approved"] = user_text == "SUBMIT"
                else:
                    confirmation["approved"] = command in {"y", "yes"}
                confirmation["event"].set()
                continue
            if (
                command == "/memory"
                or command.startswith("/memory ")
                or command == "/mem"
                or command.startswith("/mem ")
            ):
                memory_parts = user_text.split(maxsplit=2)
                subcommand = memory_parts[1].lower() if len(memory_parts) > 1 else ""
                if subcommand == "list" and len(memory_parts) == 2:
                    print(f"{DIM}{list_facts()}{RESET}\n")
                elif subcommand == "forget" and len(memory_parts) == 3 and memory_parts[2].strip():
                    print(f"{DIM}{forget_fact(memory_parts[2])}{RESET}\n")
                elif subcommand == "clear" and len(memory_parts) == 2:
                    print(f"\n{YELLOW}Jarvis wants to:{RESET} Clear all remembered facts.")
                    print(f"{YELLOW}This cannot be undone. Proceed? [y/N]:{RESET}")
                    try:
                        approved = input().strip().lower() in {"y", "yes"}
                    except (EOFError, KeyboardInterrupt):
                        approved = False
                        print()
                    if approved:
                        print(f"{DIM}{clear_all_facts()}{RESET}\n")
                    else:
                        print(f"{YELLOW}Jarvis:{RESET} Memory clear cancelled.\n")
                else:
                    print(
                        f"{YELLOW}Usage:{RESET} /memory list | "
                        "/memory forget <text> | /memory clear\n"
                    )
                continue
            if (
                command == "/macro"
                or command.startswith("/macro ")
                or command == "/mac"
                or command.startswith("/mac ")
            ):
                macro_parts = user_text.split(maxsplit=2)
                subcommand = macro_parts[1].lower() if len(macro_parts) > 1 else ""
                if subcommand == "save" and len(macro_parts) == 3:
                    if last_typed_request is None:
                        print(f"{YELLOW}Jarvis:{RESET} No previous typed request to save.\n")
                    else:
                        result = save_macro(macro_parts[2], last_typed_request)
                        print(
                            f"{DIM}{result} Saved request: {last_typed_request}{RESET}\n"
                        )
                elif subcommand == "run" and len(macro_parts) == 3:
                    request_text = get_macro(macro_parts[2])
                    if request_text is None:
                        print(
                            f"{YELLOW}Jarvis:{RESET} No macro found named "
                            f"'{macro_parts[2]}'. Available macros:\n{list_macros()}\n"
                        )
                    else:
                        # Macros replay a request, not a recorded tool-call sequence.
                        # They therefore use the normal queue and full confirmation
                        # flow every time; do not optimize this safety boundary away.
                        session.submit(request_text)
                        print(f"{DIM}Running macro '{macro_parts[2]}'.{RESET}\n")
                elif subcommand == "list" and len(macro_parts) == 2:
                    print(f"{DIM}{list_macros()}{RESET}\n")
                elif subcommand == "delete" and len(macro_parts) == 3:
                    print(f"{DIM}{delete_macro(macro_parts[2])}{RESET}\n")
                else:
                    print(
                        f"{YELLOW}Usage:{RESET} /macro save <name> | "
                        "/macro run <name> | /macro list | /macro delete <name>\n"
                    )
                continue
            if command in {"/v", "/voice"}:
                if not VOICE_ENABLED:
                    print(f"{RED}Jarvis error:{RESET} {VOICE_DEPENDENCY_ERROR}\n")
                else:
                    session.submit_voice()
            else:
                if command != "/undo":
                    last_typed_request = user_text
                session.submit("undo" if command == "/undo" else user_text)
    finally:
        session.stop()
        print(f"{DIM}Browser closed. Goodbye.{RESET}")


if __name__ == "__main__":
    main()
