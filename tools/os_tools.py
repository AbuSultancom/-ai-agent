import logging
import platform
import subprocess

from core.config import config

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

_BLOCKED_PATTERNS = [
    "rm -rf /",
    "dd if=",
    ":(){:|:&};:",  # fork bomb
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
    # Windows-specific dangerous patterns
    "format c:",
    "del /f /s /q c:\\",
    "rd /s /q c:\\",
    "reg delete hklm",
]


class OSTools:
    def execute_bash(self, command: str, timeout: int | None = None) -> str:
        """Execute a shell command safely and return combined stdout/stderr.

        On Windows, commands run via cmd /c. On Linux/macOS via bash shell=True.
        """
        if timeout is None:
            timeout = config.BASH_TIMEOUT

        cmd_lower = command.lower()
        for blocked in _BLOCKED_PATTERNS:
            if blocked in cmd_lower:
                return f"ERROR: Command blocked for safety: contains '{blocked}'"

        logger.debug("Executing command: %s", command[:200])
        try:
            if _IS_WINDOWS:
                # Translate common Unix commands to Windows equivalents
                command = _unix_to_windows(command)
                run_args = ["cmd", "/c", command]
                result = subprocess.run(
                    run_args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            else:
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
        cmd = f"where {program}" if _IS_WINDOWS else f"which {program}"
        return self.execute_bash(cmd)

    def env(self, var: str | None = None) -> str:
        if _IS_WINDOWS:
            return self.execute_bash(f"echo %{var}%" if var else "set")
        return self.execute_bash(f"echo ${var}" if var else "env")


def _unix_to_windows(cmd: str) -> str:
    """Translate basic Unix shell commands to Windows cmd equivalents."""
    mappings = [
        ("ls -la", "dir"),
        ("ls -l", "dir"),
        ("ls ", "dir "),
        ("ls", "dir"),
        ("cat ", "type "),
        ("rm -rf ", "rd /s /q "),
        ("rm -f ", "del /f /q "),
        ("rm ", "del "),
        ("cp ", "copy "),
        ("mv ", "move "),
        ("mkdir -p ", "mkdir "),
        ("touch ", "type nul > "),
        ("clear", "cls"),
        ("pwd", "cd"),
        ("grep ", "findstr "),
        ("which ", "where "),
        ("echo $", "echo %"),
    ]
    for unix, win in mappings:
        if cmd.strip().startswith(unix.strip()) or cmd == unix.strip():
            return cmd.replace(unix, win, 1)
    return cmd
