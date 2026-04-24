"""Analyst Agent — specialized in reasoning, problem decomposition, and synthesis."""

import logging
import anthropic

from core.config import config

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert analytical thinker and problem solver.
Your role in the multi-agent team:
- Break down complex problems into clear components
- Apply logical, systematic reasoning
- Identify assumptions, risks, and trade-offs
- Synthesize multiple perspectives into optimal solutions
- Provide structured decision frameworks and recommendations

When analyzing:
- Use structured thinking (pros/cons, decision trees, frameworks)
- Question assumptions explicitly
- Quantify trade-offs where possible
- Provide clear, actionable recommendations

Respond with rigorous analysis and well-reasoned conclusions."""


class AnalystAgent:
    name = "analyst"
    description = "Analytical thinker — reasons, decomposes problems, synthesizes solutions"
    emoji = "📊"

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

    def propose(self, task: str) -> str:
        return self._call([{
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                "Provide your analytical solution. Include: problem decomposition, "
                "key considerations, trade-off analysis, and your recommended approach."
            ),
        }])

    def critique(self, task: str, proposals: dict[str, str]) -> str:
        others = "\n\n".join(
            f"=== {name.upper()} AGENT ===\n{text}"
            for name, text in proposals.items()
            if name != self.name
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Other agents proposed:\n{others}\n\n"
            "From an analytical perspective, critique these proposals. "
            "Identify logical gaps, unstated assumptions, missing trade-offs, "
            "or better solution approaches. Be rigorous."
        )
        return self._call([{"role": "user", "content": prompt}])

    def refine(self, task: str, original: str, critiques: dict[str, str]) -> str:
        critique_text = "\n\n".join(
            f"[{name}]: {text}" for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Your original analysis:\n{original}\n\n"
            f"Critiques received:\n{critique_text}\n\n"
            "Refine your analysis addressing the valid critique points."
        )
        return self._call([{"role": "user", "content": prompt}])

    def synthesize(self, task: str, proposals: dict[str, str], critiques: dict[str, str]) -> str:
        """Final synthesis — combines all proposals and critiques into the optimal answer."""
        proposals_text = "\n\n".join(
            f"=== {name.upper()} PROPOSAL ===\n{text}"
            for name, text in proposals.items()
        )
        critiques_text = "\n\n".join(
            f"=== {name.upper()} CRITIQUE ===\n{text}"
            for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"PROPOSALS FROM TEAM:\n{proposals_text}\n\n"
            f"CRITIQUES FROM TEAM:\n{critiques_text}\n\n"
            "As the synthesizer, produce the final optimal answer that:\n"
            "1. Incorporates the best elements from all proposals\n"
            "2. Addresses the valid critiques\n"
            "3. Resolves any conflicts between perspectives\n"
            "4. Presents a clear, complete, actionable solution\n\n"
            "This is the final answer delivered to the user — make it excellent."
        )
        return self._call([{"role": "user", "content": prompt}], max_tokens=6000)

    def run(self, task: str, context: str = "") -> str:
        msg = task if not context else f"Context:\n{context}\n\nTask: {task}"
        return self._call([{"role": "user", "content": msg}])
