import json
import logging

import anthropic

from core.config import config

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """You are a task planning expert. Given a complex task, break it into a numbered list of concrete, actionable steps.
Each step must be self-contained and specific enough for an AI agent to execute with tools.
Respond ONLY with a JSON array of step objects: [{"step": 1, "action": "...", "rationale": "..."}]
Keep steps focused and achievable — typically 3-8 steps for most tasks."""


class PlannerAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def decompose(self, task: str) -> list[dict]:
        """Use Claude to decompose a task into executable steps."""
        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=_PLANNER_SYSTEM,
            messages=[{"role": "user", "content": f"Task to decompose:\n\n{task}"}],
        )

        text = next(
            (b.text for b in response.content if b.type == "text"), "[]"
        )

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            steps = json.loads(text)
            if isinstance(steps, list):
                return steps
        except json.JSONDecodeError:
            logger.warning("Planner returned non-JSON: %s", text[:200])

        # Fallback: treat each line as a step
        lines = [l.strip(" -•*123456789.") for l in text.splitlines() if l.strip()]
        return [{"step": i + 1, "action": line} for i, line in enumerate(lines) if line]

    def format_plan(self, task: str) -> str:
        steps = self.decompose(task)
        lines = [f"**Plan for:** {task}\n"]
        for s in steps:
            n = s.get("step", "?")
            action = s.get("action", str(s))
            rationale = s.get("rationale", "")
            lines.append(f"{n}. {action}")
            if rationale:
                lines.append(f"   _{rationale}_")
        return "\n".join(lines)
