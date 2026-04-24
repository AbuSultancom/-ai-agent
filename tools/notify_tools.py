"""Desktop notification tools — notify-send wrapper + system resource monitor."""

import logging
import shutil
import subprocess
import threading
import time
from typing import Callable

import psutil

logger = logging.getLogger(__name__)

# Alert thresholds (percent)
CPU_THRESHOLD = 85
MEM_THRESHOLD = 85
DISK_THRESHOLD = 90


def send_notification(
    title: str,
    body: str = "",
    urgency: str = "normal",   # low | normal | critical
    icon: str = "dialog-information",
    timeout_ms: int = 5000,
) -> bool:
    """
    Send a desktop notification via notify-send (libnotify).
    Falls back to logger.info if notify-send is not installed.
    """
    if not shutil.which("notify-send"):
        logger.info("NOTIFY [%s]: %s — %s", urgency, title, body)
        return False
    try:
        subprocess.run(
            [
                "notify-send",
                f"--urgency={urgency}",
                f"--icon={icon}",
                f"--expire-time={timeout_ms}",
                title,
                body,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.warning("notify-send error: %s", e)
        return False


def get_system_resources() -> dict:
    """Return current CPU, memory, disk, and top processes."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    top_procs = []
    try:
        procs = sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent") or 0,
            reverse=True,
        )[:5]
        top_procs = [
            {
                "pid": p.info["pid"],
                "name": p.info["name"],
                "cpu": round(p.info.get("cpu_percent") or 0, 1),
                "mem": round(p.info.get("memory_percent") or 0, 1),
            }
            for p in procs
        ]
    except Exception:
        pass

    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / 1e9, 2),
        "memory_total_gb": round(mem.total / 1e9, 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "net_sent_mb": round(net.bytes_sent / 1e6, 1),
        "net_recv_mb": round(net.bytes_recv / 1e6, 1),
        "top_processes": top_procs,
    }


def check_and_alert() -> dict:
    """Check resources and fire desktop notifications if thresholds are exceeded."""
    res = get_system_resources()
    alerts = []

    if res["cpu_percent"] > CPU_THRESHOLD:
        msg = f"CPU at {res['cpu_percent']}%"
        send_notification("⚠️ High CPU Usage", msg, urgency="critical", icon="cpu")
        alerts.append({"type": "cpu", "message": msg})

    if res["memory_percent"] > MEM_THRESHOLD:
        msg = f"RAM at {res['memory_percent']}% ({res['memory_used_gb']:.1f}/{res['memory_total_gb']:.1f} GB)"
        send_notification("⚠️ High Memory Usage", msg, urgency="critical", icon="memory")
        alerts.append({"type": "memory", "message": msg})

    if res["disk_percent"] > DISK_THRESHOLD:
        msg = f"Disk at {res['disk_percent']}% ({res['disk_used_gb']:.0f}/{res['disk_total_gb']:.0f} GB)"
        send_notification("⚠️ Low Disk Space", msg, urgency="critical", icon="drive-harddisk")
        alerts.append({"type": "disk", "message": msg})

    res["alerts"] = alerts
    return res


# ── Background monitor ─────────────────────────────────────────────────────

_monitor_thread: threading.Thread | None = None
_monitor_running = False
_monitor_interval = 60  # seconds
_alert_callbacks: list[Callable] = []


def add_alert_callback(fn: Callable) -> None:
    _alert_callbacks.append(fn)


def _monitor_loop():
    global _monitor_running
    while _monitor_running:
        try:
            result = check_and_alert()
            if result.get("alerts"):
                for cb in _alert_callbacks:
                    try:
                        cb(result)
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Monitor error: %s", e)
        time.sleep(_monitor_interval)


def start_monitor(interval_s: int = 60) -> bool:
    global _monitor_thread, _monitor_running, _monitor_interval
    if _monitor_running:
        return False
    _monitor_interval = interval_s
    _monitor_running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="resource-monitor")
    _monitor_thread.start()
    logger.info("Resource monitor started (interval=%ds)", interval_s)
    return True


def stop_monitor() -> bool:
    global _monitor_running
    if not _monitor_running:
        return False
    _monitor_running = False
    logger.info("Resource monitor stopped")
    return True


def monitor_status() -> dict:
    return {
        "running": _monitor_running,
        "interval_s": _monitor_interval,
        "notify_send_available": bool(shutil.which("notify-send")),
    }
