"""Researcher Agent — specialized in web search, fact-finding, and synthesis."""

import logging
import requests
from bs4 import BeautifulSoup
import anthropic

from core.config import config

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert research analyst with strong critical thinking and information synthesis skills.
Your role in the multi-agent team:
- Search for and gather relevant, up-to-date information
- Evaluate source credibility and identify reliable data
- Synthesize information from multiple sources into clear summaries
- Identify knowledge gaps and uncertainties
- Provide well-structured research reports with sources cited

When researching:
- Be objective and evidence-based
- Acknowledge uncertainty when information is unclear
- Prioritize authoritative sources
- Structure findings clearly with key points highlighted

Respond with well-organized research findings."""


class ResearcherAgent:
    name = "researcher"
    description = "Research analyst — searches, gathers, and synthesizes information"
    emoji = "🔍"

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def _call(self, messages: list[dict], max_tokens: int = 4096) -> str:
        resp = self._client.messages.create(
            model=config.MODEL,
            max_tokens=max_tokens,
            system=_SYSTEM,
            messages=messages,
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def _fetch_url(self, url: str, timeout: int = 10) -> str:
        """Fetch and extract text from a URL."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (research bot)"}
            r = requests.get(url, timeout=timeout, headers=headers)
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)[:6000]
        except Exception as e:
            return f"[fetch error: {e}]"

    def search_and_summarize(self, query: str) -> str:
        """Synthesize knowledge about a query using model knowledge + structured reasoning."""
        prompt = (
            f"Research query: {query}\n\n"
            "Provide a comprehensive research report including:\n"
            "1. Key findings and facts\n"
            "2. Important context and background\n"
            "3. Different perspectives or approaches\n"
            "4. Practical implications\n"
            "5. Key uncertainties or areas needing more information\n\n"
            "Be thorough and cite specific technical details where relevant."
        )
        return self._call([{"role": "user", "content": prompt}])

    def fetch_and_analyze(self, url: str, question: str = "") -> str:
        """Fetch content from a URL and analyze it."""
        content = self._fetch_url(url)
        q = question or "Summarize the key information from this content."
        prompt = f"URL content:\n{content}\n\nQuestion: {q}"
        return self._call([{"role": "user", "content": prompt}])

    def propose(self, task: str) -> str:
        """Generate a research-based solution for the given task."""
        return self._call([{
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                "Provide your research-based analysis and recommendations. "
                "Include relevant facts, context, and evidence-backed conclusions."
            ),
        }])

    def critique(self, task: str, proposals: dict[str, str]) -> str:
        """Review other agents' proposals for factual accuracy and completeness."""
        others = "\n\n".join(
            f"=== {name.upper()} AGENT ===\n{text}"
            for name, text in proposals.items()
            if name != self.name
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Other agents proposed:\n{others}\n\n"
            "From a research and factual accuracy perspective, critique these proposals. "
            "Check for missing context, factual errors, incomplete analysis, or better approaches. "
            "Be specific and evidence-based."
        )
        return self._call([{"role": "user", "content": prompt}])

    def refine(self, task: str, original: str, critiques: dict[str, str]) -> str:
        """Refine the original research based on critiques."""
        critique_text = "\n\n".join(
            f"[{name}]: {text}" for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Your original analysis:\n{original}\n\n"
            f"Critiques received:\n{critique_text}\n\n"
            "Refine your research, addressing valid points and filling gaps."
        )
        return self._call([{"role": "user", "content": prompt}])

    def run(self, task: str, context: str = "") -> str:
        """Direct task execution — no debate."""
        msg = task if not context else f"Context:\n{context}\n\nTask: {task}"
        return self.search_and_summarize(msg)
