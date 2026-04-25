"""Coder Agent — specialized in writing, reviewing, and debugging code."""

import logging

from core import model_router

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert software engineer with deep knowledge across all programming languages.
Your role in the multi-agent team:
- Write clean, production-quality code with clear structure
- Debug and fix code issues with root-cause analysis
- Review code for correctness, security, and performance
- Explain code and architecture decisions clearly

When writing code:
- Always include imports
- Handle errors appropriately
- Write efficient, readable code
- Provide brief usage examples when helpful

Respond with concrete code and explanations. Be precise and technical."""


class CoderAgent:
    name = "coder"
    description = "Expert software engineer — writes, reviews, and debugs code"
    emoji = "👨‍💻"

    def _call(self, messages: list[dict], max_tokens: int = 4096) -> str:
        result = model_router.chat(messages, system=_SYSTEM, max_tokens=max_tokens)
        return result if isinstance(result, str) else "".join(result)

    def propose(self, task: str) -> str:
        """Generate a coding solution for the given task."""
        return self._call([{"role": "user", "content": f"Task: {task}\n\nProvide your coding solution:"}])

    def critique(self, task: str, proposals: dict[str, str]) -> str:
        """Review other agents' proposals from a coding quality perspective."""
        others = "\n\n".join(
            f"=== {name.upper()} AGENT ===\n{text}"
            for name, text in proposals.items()
            if name != self.name
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Other agents proposed:\n{others}\n\n"
            "From a software engineering perspective, critique these proposals. "
            "Point out any code issues, missing edge cases, security concerns, or improvements needed. "
            "Be specific and constructive."
        )
        return self._call([{"role": "user", "content": prompt}])

    def refine(self, task: str, original: str, critiques: dict[str, str]) -> str:
        """Refine the original proposal based on critiques."""
        critique_text = "\n\n".join(
            f"[{name}]: {text}" for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Your original proposal:\n{original}\n\n"
            f"Critiques received:\n{critique_text}\n\n"
            "Refine your solution, addressing the valid critiques. "
            "Produce the final, improved version."
        )
        return self._call([{"role": "user", "content": prompt}])

    def run(self, task: str, context: str = "") -> str:
        """Direct task execution — no debate."""
        msg = task if not context else f"Context:\n{context}\n\nTask: {task}"
        return self._call([{"role": "user", "content": msg}])
