"""Browser Automation — Playwright-based full browser control."""

import logging
import os
import uuid

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = os.path.join("data", "screenshots")


def _ensure_dir() -> str:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    return SCREENSHOTS_DIR


class BrowserTools:
    def __init__(self):
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=True)
            except ImportError:
                raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")
        return self._browser

    def screenshot(self, url: str, full_page: bool = True) -> dict:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            shot_id = uuid.uuid4().hex[:10]
            path = os.path.join(_ensure_dir(), f"shot_{shot_id}.png")
            page.screenshot(path=path, full_page=full_page)
            return {"shot_id": shot_id, "path": path, "url": f"/api/screenshots/{shot_id}"}
        finally:
            page.close()

    def get_text(self, url: str) -> str:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return page.inner_text("body")
        finally:
            page.close()

    def click_and_get(self, url: str, selector: str) -> str:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.click(selector)
            page.wait_for_load_state("networkidle")
            return page.inner_text("body")
        finally:
            page.close()

    def fill_form(self, url: str, fields: dict[str, str], submit_selector: str = "") -> dict:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            for selector, value in fields.items():
                page.fill(selector, value)
            if submit_selector:
                page.click(submit_selector)
                page.wait_for_load_state("networkidle")
            shot_id = uuid.uuid4().hex[:10]
            path = os.path.join(_ensure_dir(), f"shot_{shot_id}.png")
            page.screenshot(path=path)
            return {
                "success": True,
                "final_url": page.url,
                "screenshot": f"/api/screenshots/{shot_id}",
            }
        finally:
            page.close()

    def extract_links(self, url: str) -> list[dict]:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))",
            )
            return links[:100]
        finally:
            page.close()

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
