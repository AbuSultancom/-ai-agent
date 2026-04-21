import glob
import logging
import os

logger = logging.getLogger(__name__)

MAX_READ_BYTES = 500_000  # 500 KB safety cap


class FileTools:
    def read_file(self, path: str) -> str:
        try:
            size = os.path.getsize(path)
            if size > MAX_READ_BYTES:
                return f"File too large ({size} bytes). Use execute_bash to read specific lines."
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as exc:
            return f"Error reading {path}: {exc}"

    def write_file(self, path: str, content: str, mode: str = "w") -> str:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)
            action = "Appended to" if mode == "a" else "Wrote"
            return f"{action} {path} ({len(content)} bytes)"
        except Exception as exc:
            return f"Error writing {path}: {exc}"

    def search_files(self, pattern: str, directory: str = ".") -> str:
        try:
            full_pattern = os.path.join(directory, pattern)
            matches = glob.glob(full_pattern, recursive=True)
            if not matches:
                return f"No files match: {full_pattern}"
            return "\n".join(sorted(matches)[:200])
        except Exception as exc:
            return f"Error searching: {exc}"

    def list_dir(self, path: str = ".") -> str:
        try:
            entries = os.listdir(path)
            lines = []
            for e in sorted(entries):
                full = os.path.join(path, e)
                kind = "d" if os.path.isdir(full) else "f"
                size = os.path.getsize(full) if kind == "f" else 0
                lines.append(f"{kind}  {size:>10}  {e}")
            return "\n".join(lines) or "(empty directory)"
        except Exception as exc:
            return f"Error listing {path}: {exc}"

    def delete_file(self, path: str) -> str:
        try:
            os.remove(path)
            return f"Deleted: {path}"
        except Exception as exc:
            return f"Error deleting {path}: {exc}"
