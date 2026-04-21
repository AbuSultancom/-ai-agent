import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """Executes a sequence of planned steps using registered tool functions."""

    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def register_tool(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn
        logger.debug("Registered tool: %s", name)

    def execute_step(self, step: dict) -> dict:
        tool_name = step.get("tool")
        params = step.get("params", {})
        action = step.get("action", "")

        if tool_name and tool_name in self._tools:
            try:
                result = self._tools[tool_name](**params)
                return {"step": step, "status": "ok", "result": result}
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tool_name, exc)
                return {"step": step, "status": "error", "error": str(exc)}

        # No tool — return the action description for the orchestrator to handle
        return {"step": step, "status": "deferred", "action": action}

    def execute_steps(self, steps: list[dict]) -> list[dict]:
        results = []
        for step in steps:
            result = self.execute_step(step)
            results.append(result)
            if result["status"] == "error":
                logger.warning("Step failed, continuing: %s", result)
        return results
