"""
Thin wrapper around Playwright exposing a small, named set of actions.

Design choice: the model never sees raw CSS selectors. Instead,
list_interactive_elements() hands back short ids ("el_1", "el_2", ...)
mapped internally to actual elements. This keeps the model's action
surface small, readable in confirmation dialogs, and easy to risk-tier.

All methods return plain strings/dicts so they can be dropped straight
back into the chat message history as tool results.
"""
import ipaddress
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import sync_playwright

from config import MAX_PAGE_TEXT_CHARS


class BrowserExecutor:
    def __init__(self, browser_name: str = "chrome", headless: bool = False):
        self._playwright = sync_playwright().start()
        browser_paths = {
            "chrome": Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "brave": Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        }
        executable_path = browser_paths.get(browser_name)
        if executable_path is None:
            self._playwright.stop()
            raise ValueError("Unsupported browser. Choose chrome or brave.")
        if not executable_path.exists():
            self._playwright.stop()
            raise RuntimeError(f"{browser_name.title()} was not found at {executable_path}.")
        self.browser = self._playwright.chromium.launch(
            executable_path=str(executable_path),
            headless=headless,
        )
        self.page = self.browser.new_page()
        self._element_map = {}  # element_id -> Playwright Locator
        self._undo_stack = []

    # ---------- low-risk (read-only) actions ----------

    def search_web(self, query: str) -> str:
        previous_url = self.page.url
        self.page.goto(f"https://www.bing.com/search?q={quote_plus(query)}")
        self.page.wait_for_load_state("domcontentloaded")
        if previous_url != "about:blank":
            self._undo_stack.append({"type": "navigate", "url": previous_url})
        return self.read_page_text()

    def open_url(self, url: str) -> str:
        raw_scheme = urlparse(url).scheme.lower()
        if raw_scheme and raw_scheme not in {"http", "https"}:
            raise ValueError("Only http and https URLs are allowed.")
        if not raw_scheme:
            url = "https://" + url
        self._validate_url(url)
        previous_url = self.page.url
        self.page.goto(url)
        self.page.wait_for_load_state("domcontentloaded")
        if previous_url != "about:blank" and previous_url != url:
            self._undo_stack.append({"type": "navigate", "url": previous_url})
        return f"Opened {url}. Current title: {self.page.title()}"

    @staticmethod
    def _validate_url(url: str):
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise ValueError("Only http and https URLs are allowed.")
        if parsed.username or parsed.password:
            raise ValueError("URLs containing embedded credentials are not allowed.")
        if hostname in {"localhost", "localhost.localdomain", "metadata.google.internal"}:
            raise ValueError("Local and cloud metadata hosts are not allowed.")
        if hostname.endswith(".local"):
            raise ValueError("Local network hostnames are not allowed.")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Private, local, or reserved IP addresses are not allowed.")

    def read_page_text(self) -> str:
        text = self.page.inner_text("body")
        text = " ".join(text.split())  # collapse whitespace
        return text[:MAX_PAGE_TEXT_CHARS]

    def list_interactive_elements(self) -> str:
        """
        Scans the page for clickable / fillable elements and returns a
        short, model-readable list like:
            el_1: button "Sign in"
            el_2: input[placeholder="Email"]
        Internally maps ids to Playwright Locators for later actions.
        """
        self._element_map.clear()
        selectors = "button, a, input, textarea, select, [role=button]"
        try:
            self.page.wait_for_selector(selectors, state="attached", timeout=2000)
        except Exception:
            pass
        locator = self.page.locator(selectors)
        count = min(locator.count(), 40)  # cap to keep context small

        lines = []
        for i in range(count):
            el = locator.nth(i)
            try:
                if not el.is_visible():
                    continue
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                text = (el.inner_text() or "").strip()[:60]
                placeholder = el.get_attribute("placeholder") or ""
                el_id = f"el_{i}"
                self._element_map[el_id] = el
                label = text or placeholder or el.get_attribute("aria-label") or ""
                lines.append(f"{el_id}: <{tag}> {label}".strip())
            except Exception:
                continue

        if not lines:
            return "No interactive elements found on the current page."
        return "\n".join(lines)

    def go_back(self) -> str:
        current_url = self.page.url
        self.page.go_back()
        if current_url != "about:blank":
            self._undo_stack.append({"type": "navigate", "url": current_url})
        return f"Went back. Current title: {self.page.title()}"

    # ---------- medium/high-risk (state-changing) actions ----------

    def click_element(self, element_id: str) -> str:
        el = self._element_map.get(element_id)
        if el is None:
            return f"Error: unknown element_id '{element_id}'. Call list_interactive_elements first."
        previous_url = self.page.url
        el.click()
        self.page.wait_for_load_state("domcontentloaded")
        if self.page.url != previous_url:
            self._undo_stack.append({"type": "navigate", "url": previous_url})
        return f"Clicked {element_id}. Current title: {self.page.title()}"

    def fill_field(self, element_id: str, value: str) -> str:
        el = self._element_map.get(element_id)
        if el is None:
            return f"Error: unknown element_id '{element_id}'. Call list_interactive_elements first."
        previous_value = el.input_value()
        el.fill(value)
        self._undo_stack.append(
            {"type": "fill", "element": el, "value": previous_value}
        )
        return f"Filled {element_id} with the given value."

    def submit_form(self, element_id: str) -> str:
        # Treated same as click, but kept as a distinct high-risk tool so it
        # is easy to gate separately (e.g. require typed confirmation later).
        return self.click_element(element_id)

    def undo_last_action(self) -> str:
        if not self._undo_stack:
            return "Nothing to undo."

        action = self._undo_stack.pop()
        if action["type"] == "navigate":
            self._validate_url(action["url"])
            self.page.goto(action["url"])
            self.page.wait_for_load_state("domcontentloaded")
            return f"Undid the last navigation. Current title: {self.page.title()}"
        if action["type"] == "fill":
            action["element"].fill(action["value"])
            return "Undid the last field change."
        return "The last action cannot be undone."

    def close(self):
        try:
            self.browser.close()
            self._playwright.stop()
        except Exception:
            pass
