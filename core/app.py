import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from flask import Flask, Response, jsonify, request, stream_with_context

from core.config import config

logging.basicConfig(level=logging.DEBUG if config.DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

# In-memory task store (replace with Redis/DB in production)
_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = threading.Lock()


def _run_task_background(task_id: str, task_text: str) -> None:
    from core.orchestrator import AIOrchestrator

    orchestrator = AIOrchestrator()
    output_chunks: list[str] = []

    with _tasks_lock:
        _tasks[task_id]["status"] = "running"

    try:
        for chunk in orchestrator.run_task(task_text):
            output_chunks.append(chunk)
            with _tasks_lock:
                _tasks[task_id]["output"] = "".join(output_chunks)

        with _tasks_lock:
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
    except Exception as e:
        logger.exception("Task %s failed", task_id)
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "AI Agent", "model": config.MODEL})


@app.route("/api/task", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    task_text = data.get("task", "").strip()

    if not task_text:
        return jsonify({"error": "task field is required"}), 400

    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _tasks[task_id] = {
            "id": task_id,
            "task": task_text,
            "status": "pending",
            "output": "",
            "created_at": datetime.utcnow().isoformat(),
        }

    thread = threading.Thread(
        target=_run_task_background, args=(task_id, task_text), daemon=True
    )
    thread.start()

    return jsonify({"task_id": task_id, "status": "pending"}), 202


@app.route("/api/task/<task_id>", methods=["GET"])
def get_task(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@app.route("/api/task/<task_id>/stream", methods=["GET"])
def stream_task(task_id: str):
    """SSE endpoint — streams task output as it arrives."""

    def generate():
        import time

        sent = 0
        for _ in range(600):  # max 10 min
            with _tasks_lock:
                task = _tasks.get(task_id)
            if not task:
                yield 'data: {"error": "not found"}\n\n'
                return

            output = task.get("output", "")
            if len(output) > sent:
                chunk = output[sent:]
                sent = len(output)
                yield f"data: {chunk}\n\n"

            status = task.get("status")
            if status in ("completed", "failed"):
                yield f"event: done\ndata: {status}\n\n"
                return

            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/task/run", methods=["POST"])
def run_task_sync():
    """Synchronous task execution — waits for completion and returns full output."""
    data = request.get_json(silent=True) or {}
    task_text = data.get("task", "").strip()

    if not task_text:
        return jsonify({"error": "task field is required"}), 400

    from core.orchestrator import AIOrchestrator

    orchestrator = AIOrchestrator()
    try:
        output = orchestrator.run_task_sync(task_text)
        return jsonify({"output": output, "status": "completed"})
    except Exception as e:
        logger.exception("Sync task failed")
        return jsonify({"error": str(e), "status": "failed"}), 500


@app.route("/api/memory/search", methods=["POST"])
def search_memory():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    n = int(data.get("n_results", 5))

    if not query:
        return jsonify({"error": "query field is required"}), 400

    from memory.memory_manager import MemoryManager

    memory = MemoryManager(config.CHROMADB_PATH)
    results = memory.search(query, n)
    return jsonify({"results": results})


@app.route("/api/memory", methods=["POST"])
def store_memory():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    content = data.get("content", "").strip()

    if not key or not content:
        return jsonify({"error": "key and content are required"}), 400

    from memory.memory_manager import MemoryManager

    memory = MemoryManager(config.CHROMADB_PATH)
    memory.store(key, content, data.get("metadata", {}))
    return jsonify({"stored": True, "key": key})


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    with _tasks_lock:
        tasks = list(_tasks.values())
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return jsonify({"tasks": tasks[:50]})


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
