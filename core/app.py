import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from core.config import config

logging.basicConfig(level=logging.DEBUG if config.DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

import os

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'))
app.config["SECRET_KEY"] = config.SECRET_KEY


@app.route("/")
def index():
    return render_template("index.html")

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
        from core.notifications import dispatch_event
        dispatch_event("task.completed", {"task_id": task_id, "task": task_text,
                                           "output_preview": "".join(output_chunks)[:300]})
    except Exception as e:
        logger.exception("Task %s failed", task_id)
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)
        from core.notifications import dispatch_event
        dispatch_event("task.failed", {"task_id": task_id, "task": task_text, "error": str(e)})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "AI Agent", "model": config.MODEL})


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    from core.auth import login
    token = login(username, password)
    if not token:
        return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"token": token, "username": username})


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    from core.auth import register
    ok = register(username, password)
    if not ok:
        return jsonify({"error": "Username taken or invalid (min 3/6 chars)"}), 400
    return jsonify({"registered": True, "username": username})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    from core.auth import get_current_user
    user = get_current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"username": user.get("sub"), "exp": user.get("exp")})


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


# ── Chat ─────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    history = data.get("history")  # optional pre-built history from client
    session_id = request.headers.get("X-Session-Id", "default")
    from core.chat import chat
    reply = chat(message, session_id=session_id, history=history)
    return jsonify({"reply": reply})


@app.route("/api/chat/clear", methods=["POST"])
def chat_clear():
    session_id = request.headers.get("X-Session-Id", "default")
    from core.chat import clear_session
    clear_session(session_id)
    return jsonify({"cleared": True})


# ── RAG ──────────────────────────────────────────────────────────────────────

@app.route("/api/rag/upload", methods=["POST"])
def rag_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    from core.rag import RAGEngine
    engine = RAGEngine(config.CHROMADB_PATH)
    result = engine.ingest_file(f)
    return jsonify(result)


@app.route("/api/rag/query", methods=["POST"])
def rag_query():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    from core.rag import RAGEngine
    engine = RAGEngine(config.CHROMADB_PATH)
    answer = engine.query(query)
    return jsonify({"answer": answer})


@app.route("/api/rag/documents", methods=["GET"])
def rag_list_docs():
    from core.rag import RAGEngine
    engine = RAGEngine(config.CHROMADB_PATH)
    return jsonify({"documents": engine.list_documents()})


@app.route("/api/rag/documents", methods=["DELETE"])
def rag_delete_doc():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    from core.rag import RAGEngine
    engine = RAGEngine(config.CHROMADB_PATH)
    engine.delete_document(name)
    return jsonify({"deleted": name})


# ── GitHub ───────────────────────────────────────────────────────────────────

@app.route("/api/github", methods=["POST"])
def github_action():
    data = request.get_json(silent=True) or {}
    action = data.pop("action", "").strip()
    if not action:
        return jsonify({"error": "action is required"}), 400
    from tools.github_tools import GitHubTools
    gh = GitHubTools()
    result = gh.dispatch(action, **data)
    return jsonify({"result": result})


# ── Multi-Agent Pipeline ─────────────────────────────────────────────────────

@app.route("/api/pipeline/run", methods=["POST"])
def pipeline_run():
    data = request.get_json(silent=True) or {}
    goal = data.get("goal", "").strip()
    if not goal:
        return jsonify({"error": "goal is required"}), 400
    from agents.pipeline import MultiAgentPipeline
    pipeline = MultiAgentPipeline()
    output = pipeline.run_sync(goal)
    return jsonify({"output": output})


# ── Code Sandbox ─────────────────────────────────────────────────────────────

@app.route("/api/code/run", methods=["POST"])
def code_run():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400
    from tools.code_sandbox import CodeSandbox
    sandbox = CodeSandbox()
    result = sandbox.execute(code, timeout=int(data.get("timeout", 15)))
    return jsonify(result)


# ── Scheduler ────────────────────────────────────────────────────────────────

@app.route("/api/scheduler/jobs", methods=["POST"])
def scheduler_add_job():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    task = data.get("task", "").strip()
    cron = data.get("cron", "").strip()
    if not name or not task or not cron:
        return jsonify({"error": "name, task, and cron are required"}), 400
    from core.scheduler import get_scheduler
    job = get_scheduler().add_job(name, task, cron)
    return jsonify(job)


@app.route("/api/scheduler/jobs", methods=["GET"])
def scheduler_list_jobs():
    from core.scheduler import get_scheduler
    return jsonify({"jobs": get_scheduler().list_jobs()})


@app.route("/api/scheduler/jobs/<job_id>", methods=["DELETE"])
def scheduler_delete_job(job_id: str):
    from core.scheduler import get_scheduler
    get_scheduler().remove_job(job_id)
    return jsonify({"deleted": job_id})


# ── Notifications & Webhooks ─────────────────────────────────────────────────

@app.route("/api/webhooks", methods=["POST"])
def webhook_register():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    from core.notifications import register_webhook
    wh = register_webhook(url, data.get("events"), data.get("secret", ""))
    return jsonify(wh), 201


@app.route("/api/webhooks", methods=["GET"])
def webhook_list():
    from core.notifications import list_webhooks
    return jsonify({"webhooks": list_webhooks()})


@app.route("/api/webhooks/<wh_id>", methods=["DELETE"])
def webhook_delete(wh_id: str):
    from core.notifications import remove_webhook
    ok = remove_webhook(wh_id)
    return jsonify({"deleted": ok})


@app.route("/api/notify/email", methods=["POST"])
def notify_email():
    data = request.get_json(silent=True) or {}
    to = data.get("to", "").strip()
    subject = data.get("subject", "AI Agent Notification")
    body = data.get("body", "").strip()
    if not to or not body:
        return jsonify({"error": "to and body are required"}), 400
    from core.notifications import send_email
    result = send_email(to, subject, body)
    return jsonify({"result": result})


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
