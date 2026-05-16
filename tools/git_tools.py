import subprocess
import logging

logger = logging.getLogger(__name__)


class GitTools:
    def _run(self, *args, cwd=None) -> str:
        try:
            result = subprocess.run(
                ["git"] + list(args), capture_output=True, text=True,
                timeout=30, cwd=cwd or "."
            )
            output = result.stdout + result.stderr
            return output.strip() or "(no output)"
        except Exception as e:
            return f"Git error: {e}"

    def status(self) -> str: return self._run("status", "--short")
    def diff(self, path: str = "") -> str:
        args = ["diff", "--stat"]
        if path: args.append(path)
        return self._run(*args)
    def log(self, n: int = 10) -> str: return self._run("log", f"--oneline", f"-{n}")
    def add(self, path: str = ".") -> str: return self._run("add", path)
    def commit(self, message: str) -> str: return self._run("commit", "-m", message)
    def push(self, branch: str = "") -> str:
        args = ["push"]
        if branch: args += ["origin", branch]
        return self._run(*args)
    def pull(self) -> str: return self._run("pull")
    def branches(self) -> str: return self._run("branch", "-a")
    def dispatch(self, action: str, **kwargs) -> str:
        actions = {
            "status": lambda: self.status(),
            "diff": lambda: self.diff(kwargs.get("path", "")),
            "log": lambda: self.log(kwargs.get("n", 10)),
            "add": lambda: self.add(kwargs.get("path", ".")),
            "commit": lambda: self.commit(kwargs.get("message", "update")),
            "push": lambda: self.push(kwargs.get("branch", "")),
            "pull": lambda: self.pull(),
            "branches": lambda: self.branches(),
        }
        fn = actions.get(action)
        return fn() if fn else f"Unknown git action: {action}"
