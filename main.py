"""Terminal entry point for Jarvis."""

import logging

from agent import Agent
from browser_executor import BrowserExecutor

RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"


def confirm_action(description: str, require_phrase: bool = False) -> bool:
    print(f"\n{YELLOW}Jarvis wants to:{RESET} {description}")
    if require_phrase:
        answer = input(f"{YELLOW}Type SUBMIT to continue (anything else cancels):{RESET} ")
        return answer == "SUBMIT"
    answer = input(f"{YELLOW}Proceed? [y/N]:{RESET} ").strip().lower()
    return answer in {"y", "yes"}


def show_status(text: str):
    print(f"{DIM}• {text}{RESET}")


def main():
    logging.basicConfig(
        filename="jarvis.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    browser = None
    agent = None

    print(f"{CYAN}╭─ Jarvis ─────────────────────────────────╮{RESET}")
    print(f"{CYAN}│ Terminal browser agent                  │{RESET}")
    print(f"{CYAN}│ Type /quit or /exit to close            │{RESET}")
    print(f"{CYAN}╰─────────────────────────────────────────╯{RESET}\n")

    try:
        browser = BrowserExecutor(headless=False)
        agent = Agent(browser, confirm_callback=confirm_action, on_status=show_status)
        while True:
            try:
                user_text = input(f"{GREEN}You:{RESET} ").strip()
            except EOFError:
                break
            if not user_text:
                continue
            if user_text.lower() in {"/quit", "/exit"}:
                break

            try:
                reply = agent.chat(user_text)
                print(f"{CYAN}Jarvis:{RESET} {reply}\n")
            except Exception as error:
                print(f"{RED}Jarvis error:{RESET} {error}\n")
    except KeyboardInterrupt:
        print("\n")
    finally:
        if agent is not None:
            agent.close()
        elif browser is not None:
            browser.close()
        print(f"{DIM}Browser closed. Goodbye.{RESET}")


if __name__ == "__main__":
    main()
