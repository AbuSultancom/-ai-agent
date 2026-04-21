"""Docker Tool — manage containers via Docker SDK or CLI fallback."""

import logging
import subprocess

logger = logging.getLogger(__name__)

_ALLOWED_IMAGES = None  # None = allow all; set a list to whitelist


def _run(cmd: list[str], timeout: int = 30) -> dict:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "ok": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out", "ok": False}
    except FileNotFoundError:
        return {"error": "docker not found in PATH", "ok": False}
    except Exception as exc:
        return {"error": str(exc), "ok": False}


class DockerTools:
    def list_containers(self, all_containers: bool = False) -> dict:
        cmd = ["docker", "ps", "--format", "json"]
        if all_containers:
            cmd.append("-a")
        return _run(cmd)

    def list_images(self) -> dict:
        return _run(["docker", "images", "--format", "json"])

    def pull(self, image: str) -> dict:
        if _ALLOWED_IMAGES is not None and image not in _ALLOWED_IMAGES:
            return {"error": f"Image '{image}' not in allowed list", "ok": False}
        return _run(["docker", "pull", image], timeout=120)

    def run_container(
        self,
        image: str,
        command: str = "",
        ports: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
        detach: bool = True,
        remove: bool = False,
    ) -> dict:
        if _ALLOWED_IMAGES is not None and image not in _ALLOWED_IMAGES:
            return {"error": f"Image '{image}' not in allowed list", "ok": False}
        cmd = ["docker", "run"]
        if detach:
            cmd.append("-d")
        if remove:
            cmd.append("--rm")
        for host_port, container_port in (ports or {}).items():
            cmd += ["-p", f"{host_port}:{container_port}"]
        for key, val in (env or {}).items():
            cmd += ["-e", f"{key}={val}"]
        cmd.append(image)
        if command:
            cmd += command.split()
        return _run(cmd, timeout=60)

    def stop(self, container_id: str) -> dict:
        return _run(["docker", "stop", container_id])

    def remove(self, container_id: str, force: bool = False) -> dict:
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container_id)
        return _run(cmd)

    def logs(self, container_id: str, tail: int = 100) -> dict:
        return _run(["docker", "logs", "--tail", str(tail), container_id])

    def stats(self, container_id: str) -> dict:
        return _run(["docker", "stats", "--no-stream", "--format", "json", container_id])

    def exec_cmd(self, container_id: str, command: str) -> dict:
        return _run(["docker", "exec", container_id] + command.split(), timeout=30)

    def inspect(self, container_id: str) -> dict:
        return _run(["docker", "inspect", container_id])
