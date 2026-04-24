"""Morning briefing generator — fetches news, checks system, summarizes with Claude."""

import logging
import time
from datetime import datetime

import anthropic
import psutil
import requests
from bs4 import BeautifulSoup

from core.config import config

logger = logging.getLogger(__name__)

_NEWS_FEEDS = [
    ("Hacker News", "https://news.ycombinator.com/rss"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
]

_BRIEFING_SYSTEM = """You are a concise morning briefing assistant.
Given news headlines and system status, produce a clear morning briefing that:
- Starts with a short greeting including the date
- Highlights 3-5 most important/interesting tech news items (1-2 sentences each)
- Gives a brief system status summary (1 sentence)
- Ends with a motivational note or key focus for the day

Keep the total briefing under 300 words. Be engaging and direct."""


def _fetch_rss(url: str, max_items: int = 5, timeout: int = 8) -> list[dict]:
    """Fetch RSS feed and return headline dicts."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "briefing-bot/1.0"})
        soup = BeautifulSoup(r.content, "xml")
        items = []
        for item in soup.find_all("item")[:max_items]:
            title = item.find("title")
            desc = item.find("description")
            items.append({
                "title": title.text.strip() if title else "",
                "description": (desc.text[:200].strip() if desc else ""),
            })
        return items
    except Exception as e:
        logger.warning("RSS fetch failed for %s: %s", url, e)
        return []


def _get_system_summary() -> str:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"CPU {cpu}% | RAM {mem.percent}% ({mem.used // 1024**3}/{mem.total // 1024**3} GB) "
        f"| Disk {disk.percent}%"
    )


def generate_briefing(custom_note: str = "") -> dict:
    """
    Generate the morning briefing.

    Returns:
        {"briefing": str, "headlines": list, "system": str, "generated_at": str}
    """
    headlines = []
    for source, url in _NEWS_FEEDS:
        items = _fetch_rss(url, max_items=3)
        for item in items:
            headlines.append({"source": source, **item})

    system_summary = _get_system_summary()
    now = datetime.now().strftime("%A, %B %d %Y — %H:%M")

    headlines_text = "\n".join(
        f"[{h['source']}] {h['title']}: {h['description']}"
        for h in headlines
    ) or "No news fetched."

    prompt = (
        f"Date/Time: {now}\n\n"
        f"News Headlines:\n{headlines_text}\n\n"
        f"System Status: {system_summary}\n"
        + (f"\nSpecial Note: {custom_note}" if custom_note else "")
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.MODEL,
        max_tokens=600,
        system=_BRIEFING_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    briefing = "".join(b.text for b in resp.content if b.type == "text")

    return {
        "briefing": briefing,
        "headlines": headlines,
        "system": system_summary,
        "generated_at": now,
    }
