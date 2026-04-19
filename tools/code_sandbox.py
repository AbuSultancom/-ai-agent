"""Safe Python code execution sandbox using subprocess with resource limits."""

import logging
import os
import subprocess
import sys
import tempfile
import textwrap

from core.config import config

logger = logging.getLogger(__name__)

# Max output size to return
MAX_OUTPUT = 20_000

# Blocked imports — prevent dangerous operations
_BLOCKED_IMPORTS = [
    "subprocess", "os.system", "shutil.rmtree", "ctypes",
    "__import__('os').system", "exec(", "eval(",
]


def _has_blocked_patterns(code: str) -> str | None:
    for pat in _BLOCKED_IMPORTS:
        if pat in code:
            return pat
    return None


class CodeSandbox:
    def execute(self, code: str, timeout: int = 15) -> dict:
        """
        Execute Python code in a subprocess and return stdout/stderr/error.
        Returns: {stdout, stderr, error, exit_code}
        """
        blocked = _has_blocked_pattern(code)
        if blocked:
            return {
                "stdout": "",
                "stderr": f"Blocked pattern: '{blocked}'",
                "error": "SecurityError",
                "exit_code": -1,
            }

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(textwrap.dedent(code))
            tmp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            stdout = result.stdout[:MAX_OUTPUT]
            stderr = result.stderr[:MAX_OUTPUT]
            return {
                "stdout": stdout,
                "stderr": stderr,
                "error": None,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "", "error": f"Timed out after {timeout}s", "exit_code": -1}
        except Exception as exc:
            return {"stdout": "", "stderr": "", "error": str(exc), "exit_code": -1}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def format_result(self, result: dict) -> str:
        parts = []
        if result.get("error"):
            parts.append(f"❌ Error: {result['error']}")
        if result.get("stdout"):
            parts.append(f"stdout:\n{result['stdout']}")
        if result.get("stderr"):
            parts.append(f"stderr:\n{result['stderr']}")
        if result.get("exit_code", 0) != 0 and not result.get("error"):
            parts.append(f"exit code: {result['exit_code']}")
        return "\n".join(parts) or "(no output)"


def _has_blocked_pattern(code: str) -> str | None:
    for pat in _BLOCKED_IMPORTS:
        if pat in code:
            return pat
    return None
