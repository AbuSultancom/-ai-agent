"""
Multi-Agent Coordinator — orchestrates specialized agents to solve complex tasks.

Modes:
  auto    — routes task to the best single agent
  debate  — agents propose → critique each other → analyst synthesizes final answer
  parallel — all agents work simultaneously, analyst synthesizes
  sequential — agents build on each other's output in a pipeline
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterator

from agents.coder_agent import CoderAgent
from agents.researcher_agent import ResearcherAgent
from agents.analyst_agent import AnalystAgent
from core import model_router

logger = logging.getLogger(__name__)

_ROUTER_SYSTEM = """You are a task routing expert. Given a task, decide which agents should handle it.

Available agents:
- coder: writing code, debugging, code review, programming questions
- researcher: factual questions, research, information gathering, explanations
- analyst: complex reasoning, decision analysis, trade-offs, planning, architecture
- all: tasks that genuinely benefit from multiple perspectives

Respond with ONLY a JSON object:
{"agents": ["coder"], "mode": "auto", "reasoning": "..."}

modes: "auto" (one agent), "debate" (agents discuss), "parallel" (all at once)"""


class MultiAgentCoordinator:
    """Orchestrates coder, researcher, and analyst agents."""

    def __init__(self):
        self.agents = {
            "coder": CoderAgent(),
            "researcher": ResearcherAgent(),
            "analyst": AnalystAgent(),
        }
        self._history: list[dict] = []
        self._lock = threading.Lock()

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route(self, task: str) -> dict:
        """Ask LLM which agents should handle this task."""
        try:
            text = model_router.chat(
                [{"role": "user", "content": task}],
                system=_ROUTER_SYSTEM,
                max_tokens=256,
            )
            if not isinstance(text, str):
                text = "".join(text)
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0:
                return json.loads(text[start:end])
        except Exception as e:
            logger.warning("Routing failed: %s", e)
        return {"agents": ["analyst"], "mode": "auto", "reasoning": "fallback"}

    # ── Execution modes ───────────────────────────────────────────────────────

    def run(self, task: str, mode: str = "auto") -> dict:
        """
        Run the multi-agent system.

        Returns:
            {
                "result": str,          # final answer
                "mode": str,
                "agents_used": list,
                "proposals": dict,      # per-agent proposals (debate/parallel)
                "critiques": dict,      # per-agent critiques (debate)
                "duration_s": float,
            }
        """
        t0 = time.time()

        if mode == "auto":
            routing = self._route(task)
            agent_names = routing.get("agents", ["analyst"])
            if "all" in agent_names:
                mode = "parallel"
                agent_names = list(self.agents.keys())
            elif len(agent_names) == 1:
                agent = self.agents.get(agent_names[0], self.agents["analyst"])
                result = agent.run(task)
                self._record(task, result, agent_names, mode)
                return {
                    "result": result,
                    "mode": "auto",
                    "agents_used": agent_names,
                    "proposals": {},
                    "critiques": {},
                    "routing_reason": routing.get("reasoning", ""),
                    "duration_s": round(time.time() - t0, 2),
                }
            else:
                mode = "parallel"

        if mode == "debate":
            return self._debate(task, t0)
        return self._parallel(task, list(self.agents.keys()), t0)

    def _parallel(self, task: str, agent_names: list[str], t0: float) -> dict:
        """All selected agents work simultaneously; analyst synthesizes."""
        proposals: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=len(agent_names)) as ex:
            futures = {
                ex.submit(self.agents[n].run, task): n
                for n in agent_names
                if n in self.agents and n != "analyst"
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    proposals[name] = future.result()
                except Exception as e:
                    proposals[name] = f"[error: {e}]"

        final = self.agents["analyst"].synthesize(task, proposals, {})
        self._record(task, final, list(proposals.keys()) + ["analyst"], "parallel")
        return {
            "result": final,
            "mode": "parallel",
            "agents_used": list(proposals.keys()) + ["analyst"],
            "proposals": proposals,
            "critiques": {},
            "duration_s": round(time.time() - t0, 2),
        }

    def _debate(self, task: str, t0: float) -> dict:
        """
        Full debate cycle:
        Round 1 — each agent proposes independently
        Round 2 — each agent critiques the others
        Round 3 — analyst synthesizes the best final answer
        """
        agent_names = list(self.agents.keys())

        # Round 1: proposals
        proposals: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=len(agent_names)) as ex:
            futures = {ex.submit(a.propose, task): name for name, a in self.agents.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    proposals[name] = future.result()
                except Exception as e:
                    proposals[name] = f"[error: {e}]"

        # Round 2: critiques (excluding analyst — it synthesizes)
        critiques: dict[str, str] = {}
        critique_agents = {n: a for n, a in self.agents.items() if n != "analyst"}
        with ThreadPoolExecutor(max_workers=len(critique_agents)) as ex:
            futures = {
                ex.submit(a.critique, task, proposals): name
                for name, a in critique_agents.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    critiques[name] = future.result()
                except Exception as e:
                    critiques[name] = f"[error: {e}]"

        # Round 3: synthesis
        final = self.agents["analyst"].synthesize(task, proposals, critiques)
        self._record(task, final, agent_names, "debate")
        return {
            "result": final,
            "mode": "debate",
            "agents_used": agent_names,
            "proposals": proposals,
            "critiques": critiques,
            "duration_s": round(time.time() - t0, 2),
        }

    def stream_run(self, task: str, mode: str = "auto") -> Iterator[str]:
        """Stream progress updates while running multi-agent task."""
        yield f"[Coordinator] Starting multi-agent task (mode={mode})\n"

        routing = {}
        if mode == "auto":
            yield "[Router] Analyzing task to select best agents…\n"
            routing = self._route(task)
            selected = routing.get("agents", ["analyst"])
            reason = routing.get("reasoning", "")
            yield f"[Router] Selected: {', '.join(selected)} — {reason}\n\n"

        yield "[Phase 1] Agents drafting proposals…\n"
        result = self.run(task, mode=mode)

        if result["mode"] in ("debate", "parallel"):
            for name, proposal in result.get("proposals", {}).items():
                agent = self.agents.get(name)
                emoji = getattr(agent, "emoji", "🤖")
                yield f"\n{emoji} [{name.upper()}] Proposal:\n{proposal}\n"

        if result.get("critiques"):
            yield "\n[Phase 2] Agents critiquing each other…\n"
            for name, critique in result["critiques"].items():
                agent = self.agents.get(name)
                emoji = getattr(agent, "emoji", "🤖")
                yield f"\n{emoji} [{name.upper()}] Critique:\n{critique}\n"

        yield f"\n[Phase 3] Analyst synthesizing final answer…\n"
        yield f"\n{'═' * 50}\n"
        yield f"FINAL ANSWER:\n{result['result']}\n"
        yield f"{'═' * 50}\n"
        yield f"\n[Done] Mode={result['mode']} | Agents={', '.join(result['agents_used'])} | Time={result['duration_s']}s\n"

    def get_agents_info(self) -> list[dict]:
        return [
            {
                "name": a.name,
                "description": a.description,
                "emoji": a.emoji,
            }
            for a in self.agents.values()
        ]

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(reversed(self._history[-50:]))

    def _record(self, task: str, result: str, agents: list[str], mode: str):
        with self._lock:
            self._history.append({
                "task": task,
                "result": result[:500],
                "agents": agents,
                "mode": mode,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })


# Singleton
_coordinator: MultiAgentCoordinator | None = None
_coord_lock = threading.Lock()


def get_coordinator() -> MultiAgentCoordinator:
    global _coordinator
    with _coord_lock:
        if _coordinator is None:
            _coordinator = MultiAgentCoordinator()
        return _coordinator
