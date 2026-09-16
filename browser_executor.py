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
import threading
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from config import MAX_PAGE_TEXT_CHARS

CHALLENGE_MARKER = "[POSSIBLE BOT-DETECTION BLOCK]"
SHORT_PAGE_TEXT_CHARS = 200
VERY_SHORT_PAGE_TEXT_CHARS = 120
CHALLENGE_PHRASES = (
    "checking your browser",
    "verify you are human",
    "attention required",
    "cloudflare",
    "captcha",
    "just a moment",
    "challenge-platform",
    "cf-chl-",
)
PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloads"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def is_likely_blocked(page) -> bool:
    """Heuristically detect a bot-detection or challenge page.

    This is not a guarantee: legitimate short pages can produce false
    positives, and unrecognized challenge pages can produce false negatives.
    Any inspection failure returns ``False`` so it never changes navigation
    failure behavior.
    """
    try:
        title = (page.title() or "").strip().lower()
    except Exception:
        title = ""

    try:
        visible_text = " ".join((page.inner_text("body") or "").split()).lower()
    except Exception:
        visible_text = ""

    combined_text = f"{title} {visible_text}"
    if any(phrase in combined_text for phrase in CHALLENGE_PHRASES):
        return True
    if "access denied" in combined_text and len(visible_text) <= SHORT_PAGE_TEXT_CHARS:
        return True

    if len(visible_text) >= VERY_SHORT_PAGE_TEXT_CHARS:
        return False

    try:
        if page.locator("iframe").count() > 0:
            return True
        challenge_selectors = (
            "#challenge-running, #challenge-stage, .cf-chl-widget, "
            "[data-cf-chl], [id*='challenge'], [class*='challenge'], "
            "iframe[src*='captcha'], iframe[src*='challenge']"
        )
        return page.locator(challenge_selectors).count() > 0
    except Exception:
        return False


class BrowserExecutor:
    def __init__(self, browser_name: str = "chrome", headless: bool = False):
        self._download_lock = threading.Lock()
        self._download_results = {}
        self._last_download = None
        self._download_setup_error = None
        try:
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as error:
            self._download_setup_error = f"Error preparing download directory: {error}"

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
        self.page.on("download", self._handle_download)
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
        result = f"Opened {url}. Current title: {self.page.title()}"
        if is_likely_blocked(self.page):
            result = f"{CHALLENGE_MARKER} {result}"
        return result

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

    def get_last_download_info(self) -> str:
        """Return details about the most recently completed download."""
        try:
            with self._download_lock:
                download = self._last_download
            if download is None:
                return "No download has occurred yet."
            return (
                f"Filename: {download['filename']}; "
                f"Saved path: {download['path']}; "
                f"Size: {self._format_file_size(download['size'])}."
            )
        except Exception as error:
            return f"Error reading last download info: {error}"

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
        download = None
        try:
            try:
                with self.page.expect_download(timeout=1500) as download_info:
                    el.click()
                download = download_info.value
            except PlaywrightTimeoutError:
                # The click completed normally without starting a download.
                pass
        except Exception as error:
            return f"Error clicking {element_id}: {error}"

        try:
            self.page.wait_for_load_state("domcontentloaded")
        except Exception as error:
            return f"Error completing click {element_id}: {error}"

        if self.page.url != previous_url:
            self._undo_stack.append({"type": "navigate", "url": previous_url})
        result = f"Clicked {element_id}. Current title: {self.page.title()}"
        if download is not None:
            with self._download_lock:
                download_result = self._download_results.get(id(download))
            if download_result is None:
                download_result = self._save_download(download)
            if download_result.startswith("Error"):
                return download_result
            return f"{result} Download started: {download_result}"
        return result

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

    def _handle_download(self, download) -> None:
        """Save a Playwright download and retain its result for click handling."""
        result = self._save_download(download)
        with self._download_lock:
            self._download_results[id(download)] = result

    def _save_download(self, download) -> str:
        try:
            if self._download_setup_error:
                return self._download_setup_error

            filename = Path(download.suggested_filename).name
            if not filename or filename in {".", ".."}:
                filename = "download"

            failure = download.failure()
            if failure:
                return f"Error downloading '{filename}': {failure}"

            source_path = Path(download.path())
            size = source_path.stat().st_size
            if size > MAX_DOWNLOAD_BYTES:
                self._cancel_download(download)
                return (
                    f"Error downloading '{filename}': file exceeds the maximum "
                    f"allowed size of {self._format_file_size(MAX_DOWNLOAD_BYTES)}."
                )

            destination = self._reserve_download_path(filename)
            try:
                download.save_as(str(destination))
                size = destination.stat().st_size
                if size > MAX_DOWNLOAD_BYTES:
                    self._cancel_download(download)
                    destination.unlink(missing_ok=True)
                    return (
                        f"Error downloading '{filename}': file exceeds the maximum "
                        f"allowed size of {self._format_file_size(MAX_DOWNLOAD_BYTES)}."
                    )
            except Exception:
                destination.unlink(missing_ok=True)
                raise

            info = {"filename": filename, "path": str(destination), "size": size}
            with self._download_lock:
                self._last_download = info
            return (
                f"Filename: {filename}; saved to {destination}; "
                f"size {self._format_file_size(size)}"
            )
        except Exception as error:
            return f"Error saving download: {error}"

    @staticmethod
    def _reserve_download_path(filename: str) -> Path:
        candidate = DOWNLOAD_DIR / filename
        suffix = 1
        while True:
            try:
                candidate.touch(exist_ok=False)
                return candidate
            except FileExistsError:
                path = Path(filename)
                candidate = DOWNLOAD_DIR / f"{path.stem}_{suffix}{path.suffix}"
                suffix += 1

    @staticmethod
    def _cancel_download(download) -> None:
        try:
            download.cancel()
        except Exception:
            pass
        try:
            download.delete()
        except Exception:
            pass

    @staticmethod
    def _format_file_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

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
