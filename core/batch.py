"""Batch Tasks — run multiple tasks concurrently and collect results."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

logger = logging.getLogger(__name__)

_MAX_WORKERS = 5


def run_batch(tasks: list[str], max_workers: int = _MAX_WORKERS) -> dict:
    """Run a list of task strings in parallel. Returns a results dict."""
    batch_id = uuid.uuid4().hex[:10]
    results = {}
    lock = threading.Lock()

    from core.orchestrator import AIOrchestrator

    def _run_one(idx: int, task_text: str) -> tuple[int, dict]:
        orchestrator = AIOrchestrator()
        start = datetime.utcnow()
        try:
            output = orchestrator.run_task_sync(task_text)
            return idx, {
                "task": task_text,
                "status": "completed",
                "output": output,
                "started_at": start.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            return idx, {
                "task": task_text,
                "status": "failed",
                "error": str(exc),
                "started_at": start.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, i, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures):
            idx, result = future.result()
            with lock:
                results[idx] = result

    ordered = [results[i] for i in sorted(results)]
    return {
        "batch_id": batch_id,
        "total": len(tasks),
        "completed": sum(1 for r in ordered if r["status"] == "completed"),
        "failed": sum(1 for r in ordered if r["status"] == "failed"),
        "results": ordered,
    }
