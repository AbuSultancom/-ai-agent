"""
Self-Healing System — detects errors in running code, generates patches,
applies them safely (with backup + syntax check), and signals a restart.

Flow:
  1. Task/tool throws an exception
  2. SelfHealer.analyze(error, context) → patch proposal from Claude
  3. SelfHealer.apply(patch) → backs up original, writes fix, validates syntax
  4. Healer records the fix in heal_log for introspection
  5. Caller re-runs the original task
"""

import ast
import importlib
import logging
import os
import re
import shutil
import sys
import textwrap
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

from core.config import config

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.resolve()
_BACKUP_DIR = _REPO_ROOT / "data" / "heal_backups"
_HEAL_LOG: list[dict] = []
_LOCK = threading.Lock()

_HEALER_SYSTEM = """You are an expert Python debugging and self-repair agent.

You will be given:
- An error traceback from a running Python application
- The source code of the file that caused the error
- The task or context that triggered the error

Your job:
1. Identify the root cause of the error precisely
2. Generate a minimal, safe patch to fix it
3. Return ONLY a JSON object in this exact format:

{
  "file": "relative/path/to/file.py",
  "analysis": "Brief explanation of the root cause",
  "confidence": 0.0-1.0,
  "patch_type": "replace_function|replace_block|add_import|fix_syntax",
  "old_code": "exact string to find and replace",
  "new_code": "exact replacement string",
  "safe_to_apply": true|false,
  "reasoning": "Why this fix is correct and safe"
}

Rules:
- Only patch files inside the project (never system files)
- Keep patches minimal — fix only what's broken
- Set safe_to_apply=false if the fix is risky or uncertain
- If you cannot determine a safe fix, set safe_to_apply=false and explain in reasoning
- The old_code must be an exact substring of the file content
"""


class SelfHealer:
    """Analyzes runtime errors and applies code patches automatically."""

    def __init__(self):
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyze(
        self,
        error: str | Exception,
        task: str = "",
        file_hint: str = "",
    ) -> dict:
        """
        Analyze an error and propose a patch.

        Returns a patch dict or {"safe_to_apply": False, "analysis": reason}.
        """
        tb = (
            "".join(traceback.format_exception(type(error), error, error.__traceback__))
            if isinstance(error, Exception)
            else str(error)
        )

        # Extract the likely source file from the traceback
        target_file = file_hint or self._extract_file_from_tb(tb)
        source = ""
        if target_file:
            try:
                full = (_REPO_ROOT / target_file).resolve()
                if full.is_relative_to(_REPO_ROOT):
                    source = full.read_text(encoding="utf-8")
            except Exception:
                pass

        prompt = (
            f"TASK: {task}\n\n"
            f"ERROR TRACEBACK:\n{tb}\n\n"
            f"TARGET FILE ({target_file}):\n```python\n{source[:8000]}\n```"
        )

        try:
            from core import model_router
            text = model_router.chat(
                [{"role": "user", "content": prompt}],
                system=_HEALER_SYSTEM,
                max_tokens=2048,
            )
            if not isinstance(text, str):
                text = "".join(text)
            import json
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0:
                patch = json.loads(text[start:end])
                patch["traceback"] = tb[:1000]
                patch["task"] = task
                return patch
        except Exception as e:
            logger.error("Healer analysis failed: %s", e)

        return {
            "safe_to_apply": False,
            "analysis": "Could not parse patch from model response",
            "traceback": tb[:1000],
            "task": task,
        }

    def _extract_file_from_tb(self, tb: str) -> str:
        """Pull the last project-internal file path from a traceback."""
        matches = re.findall(r'File "([^"]+\.py)"', tb)
        for path in reversed(matches):
            p = Path(path)
            try:
                rel = p.relative_to(_REPO_ROOT)
                # Skip test files and external packages
                if not any(part.startswith(".") for part in rel.parts):
                    return str(rel)
            except ValueError:
                continue
        return ""

    # ── Patching ──────────────────────────────────────────────────────────────

    def apply(self, patch: dict) -> dict:
        """
        Apply a patch dict returned by analyze().

        Returns {"applied": bool, "file": str, "backup": str, "error": str|None}
        """
        if not patch.get("safe_to_apply", False):
            return {
                "applied": False,
                "file": patch.get("file", ""),
                "reason": patch.get("reasoning", "Marked unsafe by healer"),
            }

        rel_path = patch.get("file", "").strip()
        if not rel_path:
            return {"applied": False, "error": "No file specified in patch"}

        target = (_REPO_ROOT / rel_path).resolve()
        # Safety: only patch files inside the repo
        if not target.is_relative_to(_REPO_ROOT):
            return {"applied": False, "error": "Patch targets a file outside the repo"}
        if not target.exists():
            return {"applied": False, "error": f"File not found: {rel_path}"}

        original = target.read_text(encoding="utf-8")
        old_code = patch.get("old_code", "")
        new_code = patch.get("new_code", "")

        if old_code and old_code not in original:
            return {"applied": False, "error": "old_code not found in file — patch is stale"}

        # Backup
        backup_name = f"{rel_path.replace('/', '_')}_{int(time.time())}.bak"
        backup_path = _BACKUP_DIR / backup_name
        shutil.copy2(target, backup_path)

        # Apply
        if old_code:
            patched = original.replace(old_code, new_code, 1)
        else:
            patched = new_code

        # Syntax check before writing
        try:
            ast.parse(patched)
        except SyntaxError as e:
            return {"applied": False, "error": f"Patch introduces syntax error: {e}", "backup": str(backup_path)}

        target.write_text(patched, encoding="utf-8")

        # Reload the module if it's already imported
        module_name = rel_path.replace("/", ".").removesuffix(".py")
        if module_name in sys.modules:
            try:
                importlib.reload(sys.modules[module_name])
                logger.info("Reloaded module: %s", module_name)
            except Exception as e:
                logger.warning("Could not hot-reload %s: %s", module_name, e)

        result = {
            "applied": True,
            "file": rel_path,
            "backup": str(backup_path),
            "analysis": patch.get("analysis", ""),
            "confidence": patch.get("confidence", 0),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._record(result, patch)
        logger.info("Self-heal applied to %s (confidence=%.2f)", rel_path, patch.get("confidence", 0))
        return result

    # ── Convenience: analyze + apply in one call ───────────────────────────────

    def heal(
        self,
        error: str | Exception,
        task: str = "",
        file_hint: str = "",
        auto_apply: bool = True,
    ) -> dict:
        """
        Full healing cycle: analyze error → optionally apply patch.

        Returns combined result dict with keys: patch, apply_result, healed (bool).
        """
        patch = self.analyze(error, task=task, file_hint=file_hint)
        apply_result = {}
        healed = False

        if auto_apply and patch.get("safe_to_apply"):
            apply_result = self.apply(patch)
            healed = apply_result.get("applied", False)

        return {"patch": patch, "apply_result": apply_result, "healed": healed}

    # ── Restore ────────────────────────────────────────────────────────────────

    def restore(self, backup_path: str) -> bool:
        """Restore a file from a backup created by apply()."""
        bp = Path(backup_path)
        if not bp.exists():
            return False
        # Reconstruct the original file path from backup filename
        # Format: path_to_file_<timestamp>.bak
        parts = bp.stem.rsplit("_", 1)[0]
        rel = parts.replace("_", "/") + ".py"
        target = (_REPO_ROOT / rel).resolve()
        if not target.is_relative_to(_REPO_ROOT):
            return False
        shutil.copy2(bp, target)
        logger.info("Restored %s from backup", rel)
        return True

    # ── Log ───────────────────────────────────────────────────────────────────

    def _record(self, result: dict, patch: dict):
        with _LOCK:
            _HEAL_LOG.append({**result, "patch_summary": patch.get("analysis", "")})
            if len(_HEAL_LOG) > 200:
                _HEAL_LOG.pop(0)

    def get_log(self) -> list[dict]:
        with _LOCK:
            return list(reversed(_HEAL_LOG))

    def list_backups(self) -> list[dict]:
        backups = []
        for f in sorted(_BACKUP_DIR.glob("*.bak"), reverse=True):
            backups.append({"name": f.name, "path": str(f), "size": f.stat().st_size,
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))})
        return backups[:50]


# ── Singleton ──────────────────────────────────────────────────────────────────

_healer: Optional[SelfHealer] = None
_healer_lock = threading.Lock()


def get_healer() -> SelfHealer:
    global _healer
    with _healer_lock:
        if _healer is None:
            _healer = SelfHealer()
        return _healer


def auto_heal(error: Exception, task: str = "", max_attempts: int = 2) -> dict:
    """
    Convenience wrapper — called from orchestrator/task runner when a task fails.
    Attempts healing up to max_attempts times.
    """
    healer = get_healer()
    for attempt in range(1, max_attempts + 1):
        logger.info("Self-heal attempt %d/%d for task: %s", attempt, max_attempts, task[:80])
        result = healer.heal(error, task=task, auto_apply=True)
        if result["healed"]:
            return result
        if not result["patch"].get("safe_to_apply"):
            break
    return {"healed": False, "patch": {}, "apply_result": {}}
