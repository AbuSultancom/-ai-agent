"""Cron-based task scheduler using APScheduler."""

import logging
import threading
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler_instance = None
_lock = threading.Lock()


def get_scheduler() -> "TaskScheduler":
    global _scheduler_instance
    with _lock:
        if _scheduler_instance is None:
            _scheduler_instance = TaskScheduler()
            _scheduler_instance.start()
    return _scheduler_instance


class TaskScheduler:
    def __init__(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            self._aps = BackgroundScheduler(timezone="UTC")
            self._CronTrigger = CronTrigger
            self._available = True
        except ImportError:
            logger.warning("APScheduler not installed. pip install apscheduler")
            self._available = False
            self._aps = None

        self._jobs: dict[str, dict] = {}  # job_id → metadata

    def start(self) -> None:
        if self._available and self._aps:
            self._aps.start()
            logger.info("Scheduler started")

    def _run_task(self, job_id: str, task: str) -> None:
        from core.orchestrator import AIOrchestrator
        logger.info("Scheduler running job %s", job_id)
        if job_id in self._jobs:
            self._jobs[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._jobs[job_id]["run_count"] = self._jobs[job_id].get("run_count", 0) + 1
        try:
            orchestrator = AIOrchestrator()
            output = orchestrator.run_task_sync(task)
            if job_id in self._jobs:
                self._jobs[job_id]["last_output"] = output[:500]
                self._jobs[job_id]["last_status"] = "ok"
        except Exception as exc:
            logger.exception("Scheduled job %s failed", job_id)
            if job_id in self._jobs:
                self._jobs[job_id]["last_status"] = f"error: {exc}"

    def add_job(self, name: str, task: str, cron: str) -> dict:
        job_id = str(uuid.uuid4())[:8]
        meta = {
            "id": job_id,
            "name": name,
            "task": task,
            "cron": cron,
            "created_at": datetime.utcnow().isoformat(),
            "run_count": 0,
            "last_run": None,
            "last_status": None,
            "next_run": None,
        }

        if self._available and self._aps:
            try:
                parts = cron.strip().split()
                if len(parts) != 5:
                    return {"error": "Invalid cron expression. Expected 5 fields: min hour dom mon dow"}
                minute, hour, day, month, day_of_week = parts
                job = self._aps.add_job(
                    self._run_task,
                    trigger=self._CronTrigger(
                        minute=minute, hour=hour, day=day,
                        month=month, day_of_week=day_of_week
                    ),
                    args=[job_id, task],
                    id=job_id,
                )
                next_fire = job.next_run_time
                meta["next_run"] = next_fire.isoformat() if next_fire else None
            except Exception as exc:
                return {"error": f"Failed to schedule: {exc}"}
        else:
            meta["note"] = "APScheduler not installed — job saved but not running"

        self._jobs[job_id] = meta
        return meta

    def remove_job(self, job_id: str) -> bool:
        self._jobs.pop(job_id, None)
        if self._available and self._aps:
            try:
                self._aps.remove_job(job_id)
            except Exception:
                pass
        return True

    def list_jobs(self) -> list[dict]:
        jobs = list(self._jobs.values())
        # Refresh next_run times from APScheduler
        if self._available and self._aps:
            for job in jobs:
                try:
                    aps_job = self._aps.get_job(job["id"])
                    if aps_job and aps_job.next_run_time:
                        job["next_run"] = aps_job.next_run_time.isoformat()
                except Exception:
                    pass
        return jobs
