import logging
import re

from core.config import config

logger = logging.getLogger(__name__)


class WebTools:
    """HTTP-based web tools using requests + BeautifulSoup.
    Falls back to plain text extraction when bs4 is unavailable."""

    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI-Agent/1.0; +https://github.com/AbuSultancom/-ai-agent)"
                )
            })
        return self._session

    def fetch(self, url: str, extract: str = "text") -> str:
        """Fetch a URL and return content based on extract mode."""
        try:
            resp = self.session.get(url, timeout=config.WEB_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if "json" in content_type:
                return resp.text[:8000]

            html = resp.text
            return self._parse_html(html, extract, url)

        except Exception as exc:
            logger.warning("web_fetch failed for %s: %s", url, exc)
            return f"Error fetching {url}: {exc}"

    def _parse_html(self, html: str, extract: str, url: str) -> str:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            if extract == "links":
                links = []
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.get_text(strip=True)
                    if href and not href.startswith("#"):
                        links.append(f"{text}: {href}")
                return "\n".join(links[:100]) or "(no links found)"

            if extract == "html":
                return str(soup)[:10000]

            # text mode
            text = soup.get_text(separator="\n", strip=True)
            # Collapse blank lines
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text[:8000]

        except ImportError:
            # bs4 not installed — strip tags with regex
            if extract == "html":
                return html[:10000]
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:8000]

    def screenshot(self, url: str, output_path: str = "screenshot.png") -> str:
        """Take a screenshot using Playwright (requires playwright to be installed)."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=config.WEB_TIMEOUT * 1000)
                page.screenshot(path=output_path, full_page=True)
                browser.close()
            return f"Screenshot saved to {output_path}"
        except ImportError:
            return "Playwright not installed. Run: pip install playwright && playwright install chromium"
        except Exception as exc:
            return f"Screenshot failed: {exc}"

    def search(self, query: str) -> str:
        """Search DuckDuckGo and return result snippets."""
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        try:
            from bs4 import BeautifulSoup
            resp = self.session.get(url, timeout=config.WEB_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result__body")[:8]:
                title_el = r.select_one(".result__title")
                snippet_el = r.select_one(".result__snippet")
                url_el = r.select_one(".result__url")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                link = url_el.get_text(strip=True) if url_el else ""
                if title:
                    results.append(f"**{title}**\n{link}\n{snippet}")
            return "\n\n".join(results) or "No results found."
        except Exception as exc:
            return f"Search failed: {exc}"
