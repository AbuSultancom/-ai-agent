"""
Multi-Agent Pipeline: Planner → Researcher → Writer → Reviewer

Each agent is a specialized Claude instance with a focused system prompt.
The pipeline passes results between stages and produces a final polished output.
"""

import logging
from collections.abc import Generator
from dataclasses import dataclass, field

import anthropic

from core.config import config

logger = logging.getLogger(__name__)

# ── Specialized system prompts ────────────────────────────────────────────────

_PLANNER_SYS = """You are a strategic task planner. Given a goal, output a clear JSON plan:
{"goal": "...", "steps": [{"id": 1, "role": "researcher|writer|analyst|reviewer", "task": "..."}]}
Keep steps focused and sequential. Maximum 5 steps."""

_RESEARCHER_SYS = """You are a thorough researcher. Given a research task, gather all relevant information,
facts, and context needed. Structure your findings clearly with headers and bullet points.
Focus on accuracy and completeness."""

_WRITER_SYS = """You are an expert writer. Given research findings and a writing task,
produce polished, well-structured content. Use clear language, proper formatting, and engaging style.
Adapt tone to the context (technical, creative, business, etc.)."""

_ANALYST_SYS = """You are a data analyst and problem solver. Given data, code, or a technical problem,
provide thorough analysis, identify patterns, suggest solutions, and explain your reasoning clearly."""

_REVIEWER_SYS = """You are a quality reviewer. Review the previous output critically:
1. Check for accuracy, completeness, and clarity
2. Identify any gaps or errors
3. Provide an improved/corrected version
4. Rate quality: Excellent / Good / Needs Work"""

ROLE_SYSTEMS = {
    "planner": _PLANNER_SYS,
    "researcher": _RESEARCHER_SYS,
    "writer": _WRITER_SYS,
    "analyst": _ANALYST_SYS,
    "reviewer": _REVIEWER_SYS,
}


@dataclass
class PipelineResult:
    goal: str
    steps: list[dict] = field(default_factory=list)
    outputs: dict[int, str] = field(default_factory=dict)
    final: str = ""


class MultiAgentPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def _call_agent(self, role: str, task: str, context: str = "") -> str:
        system = ROLE_SYSTEMS.get(role, ROLE_SYSTEMS["writer"])
        content = task if not context else f"Context from previous steps:\n{context}\n\nYour task: {task}"
        try:
            resp = self.client.messages.create(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
            )
            return next((b.text for b in resp.content if b.type == "text"), "")
        except Exception as exc:
            logger.exception("Agent %s failed", role)
            return f"[Error in {role}: {exc}]"

    def _plan(self, goal: str) -> list[dict]:
        import json
        raw = self._call_agent("planner", goal)
        # Strip markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(raw)
            return data.get("steps", [])
        except Exception:
            # Fallback: single researcher + writer + reviewer
            return [
                {"id": 1, "role": "researcher", "task": f"Research everything needed for: {goal}"},
                {"id": 2, "role": "writer", "task": f"Write the final output for: {goal}"},
                {"id": 3, "role": "reviewer", "task": "Review and improve the previous output"},
            ]

    def run(self, goal: str) -> Generator[str, None, None]:
        yield f"🎯 **الهدف:** {goal}\n\n"
        yield "🗺️ **التخطيط…**\n"

        steps = self._plan(goal)
        yield f"خطة من {len(steps)} خطوات\n\n"

        result = PipelineResult(goal=goal, steps=steps)
        accumulated_context = ""

        for step in steps:
            step_id = step.get("id", "?")
            role = step.get("role", "writer")
            task = step.get("task", goal)

            icon = {"researcher": "🔍", "writer": "✍️", "analyst": "📊", "reviewer": "🔎"}.get(role, "🤖")
            yield f"\n{icon} **الخطوة {step_id} — {role}**\n"
            yield f"_{task}_\n\n"

            output = self._call_agent(role, task, accumulated_context)
            result.outputs[step_id] = output
            accumulated_context = f"Step {step_id} ({role}):\n{output}"

            yield output
            yield "\n\n---\n\n"

        result.final = result.outputs.get(max(result.outputs.keys(), default=1), "")
        yield f"✅ **اكتمل pipeline من {len(steps)} مراحل**\n"

    def run_sync(self, goal: str) -> str:
        return "".join(self.run(goal))
