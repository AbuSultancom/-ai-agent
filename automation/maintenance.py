"""System maintenance automation — temp file cleanup, log rotation, disk reports."""

import glob
import logging
import os
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMP_PATTERNS = [
    "/tmp/*.tmp",
    "/tmp/tmp*",
    "/var/tmp/*.tmp",
    os.path.expanduser("~/.cache/thumbnails/fail/"),
    os.path.expanduser("~/.local/share/Trash/files/"),
]

_LOG_DIRS = ["/var/log"]
_LOG_MAX_DAYS = 30


def clean_temp_files(dry_run: bool = False) -> dict:
    """Delete temporary files matching known patterns."""
    removed = []
    errors = []
    total_bytes = 0

    for pattern in _TEMP_PATTERNS:
        # Handle directory targets
        if pattern.endswith("/"):
            path = Path(pattern)
            if path.exists() and path.is_dir():
                try:
                    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                    if not dry_run:
                        shutil.rmtree(path, ignore_errors=True)
                        path.mkdir(parents=True, exist_ok=True)
                    removed.append({"path": str(path), "size_mb": round(size / 1e6, 2), "type": "directory"})
                    total_bytes += size
                except Exception as e:
                    errors.append({"path": str(path), "error": str(e)})
            continue

        for filepath in glob.glob(pattern):
            try:
                p = Path(filepath)
                if not p.exists():
                    continue
                size = p.stat().st_size
                age_days = (time.time() - p.stat().st_mtime) / 86400
                if age_days < 1:
                    continue
                if not dry_run:
                    p.unlink(missing_ok=True)
                removed.append({
                    "path": filepath,
                    "size_mb": round(size / 1e6, 3),
                    "age_days": round(age_days, 1),
                    "type": "file",
                })
                total_bytes += size
            except Exception as e:
                errors.append({"path": filepath, "error": str(e)})

    return {
        "removed_count": len(removed),
        "total_freed_mb": round(total_bytes / 1e6, 2),
        "items": removed,
        "errors": errors,
        "dry_run": dry_run,
    }


def clean_old_logs(max_days: int = _LOG_MAX_DAYS, dry_run: bool = False) -> dict:
    """Remove log files older than max_days from /var/log."""
    removed = []
    errors = []
    total_bytes = 0
    cutoff = time.time() - max_days * 86400

    for log_dir in _LOG_DIRS:
        if not os.path.isdir(log_dir):
            continue
        for root, _, files in os.walk(log_dir):
            for fname in files:
                if not (fname.endswith(".gz") or fname.endswith(".old") or fname.endswith(".1")):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    stat = os.stat(fpath)
                    if stat.st_mtime < cutoff:
                        size = stat.st_size
                        if not dry_run:
                            os.unlink(fpath)
                        removed.append({"path": fpath, "size_mb": round(size / 1e6, 3)})
                        total_bytes += size
                except Exception as e:
                    errors.append({"path": fpath, "error": str(e)})

    return {
        "removed_count": len(removed),
        "total_freed_mb": round(total_bytes / 1e6, 2),
        "items": removed[:20],
        "errors": errors[:5],
        "dry_run": dry_run,
    }


def disk_report() -> dict:
    """Return disk usage report for key directories."""
    try:
        import psutil
        disk = psutil.disk_usage("/")
        home = Path.home()
        report = {
            "root": {
                "total_gb": round(disk.total / 1e9, 2),
                "used_gb": round(disk.used / 1e9, 2),
                "free_gb": round(disk.free / 1e9, 2),
                "percent": disk.percent,
            },
        }
        # Top dirs in home
        top_dirs = []
        if home.exists():
            for d in sorted(home.iterdir(), key=lambda p: _dir_size(p), reverse=True)[:8]:
                if d.is_dir():
                    sz = _dir_size(d)
                    if sz > 10 * 1024 * 1024:
                        top_dirs.append({"path": str(d), "size_mb": round(sz / 1e6, 1)})
        report["home_dirs"] = top_dirs
        return report
    except Exception as e:
        return {"error": str(e)}


def _dir_size(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except Exception:
        return 0


def run_all_maintenance(dry_run: bool = False) -> dict:
    """Run full maintenance suite."""
    return {
        "temp_cleanup": clean_temp_files(dry_run=dry_run),
        "log_cleanup": clean_old_logs(dry_run=dry_run),
        "disk_report": disk_report(),
    }
