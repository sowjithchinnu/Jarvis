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
        browser_name = choose_browser()
        if browser_name is None:
            print(f"{DIM}Goodbye.{RESET}")
            return
        browser = BrowserExecutor(browser_name=browser_name, headless=False)
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
            if user_text.lower() == "/undo":
                try:
                    description = "Undo the most recent reversible browser action."
                    if confirm_action(description):
                        result = agent._execute_tool("undo_last_action", {})
                    else:
                        result = "Undo cancelled."
                    print(f"{CYAN}Jarvis:{RESET} {result}\n")
                except Exception:
                    logging.getLogger(__name__).exception("Undo failed")
                    print(f"{RED}Jarvis error:{RESET} Undo failed. See jarvis.log for details.\n")
                continue

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
