import logging
import platform
import subprocess

from core.config import config

logger = logging.getLogger(__name__)

# Commands that are too dangerous to run
_BLOCKED_PATTERNS = [
    "rm -rf /",
    "dd if=",
    ":(){:|:&};:",  # fork bomb
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
]


class OSTools:
    def execute_bash(self, command: str, timeout: int | None = None) -> str:
        """Execute a bash command safely and return combined stdout/stderr."""
        if timeout is None:
            timeout = config.BASH_TIMEOUT

        cmd_lower = command.lower()
        for blocked in _BLOCKED_PATTERNS:
            if blocked in cmd_lower:
                return f"ERROR: Command blocked for safety: contains '{blocked}'"

        logger.debug("Executing bash: %s", command[:200])
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if result.returncode != 0:
                output = f"[exit {result.returncode}]\n{output}"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"ERROR: Command timed out after {timeout}s"
        except Exception as exc:
            return f"ERROR: {exc}"

    def get_system_info(self) -> dict:
        return {
            "os": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }

    def which(self, program: str) -> str:
        return self.execute_bash(f"which {program}")

    def env(self, var: str | None = None) -> str:
        if var:
            return self.execute_bash(f"echo ${var}")
        return self.execute_bash("env")
