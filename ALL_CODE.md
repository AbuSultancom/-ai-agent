# AI Agent — Complete Source Code

Generated: Sat Apr 25 05:19:06 UTC 2026


---

## `orchestrator.py`

```py
"""
Main entry point for the AI Agent.

Run modes:
  python orchestrator.py serve          — start Flask API server
  python orchestrator.py run "task..."  — execute a single task from CLI
  python orchestrator.py plan "task..."  — show planning steps only
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_serve() -> None:
    from core.app import app
    from core.config import config
    logger.info("Starting AI Agent API on %s:%s", config.HOST, config.PORT)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


def cmd_run(task: str) -> None:
    from core.orchestrator import AIOrchestrator
    orchestrator = AIOrchestrator()
    print(f"\n{'='*60}")
    print(f"Task: {task}")
    print("=" * 60)
    for chunk in orchestrator.run_task(task):
        print(chunk, end="", flush=True)
    print("\n" + "=" * 60)


def cmd_plan(task: str) -> None:
    from agents.planner_agent import PlannerAgent
    planner = PlannerAgent()
    print(planner.format_plan(task))


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Agent")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start Flask API server")

    run_p = subparsers.add_parser("run", help="Run a task directly")
    run_p.add_argument("task", nargs="+", help="Task description")

    plan_p = subparsers.add_parser("plan", help="Show task plan without executing")
    plan_p.add_argument("task", nargs="+", help="Task description")

    args = parser.parse_args()

    if args.command == "serve" or args.command is None:
        cmd_serve()
    elif args.command == "run":
        cmd_run(" ".join(args.task))
    elif args.command == "plan":
        cmd_plan(" ".join(args.task))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

```

---

## `core/config.py`

```py
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Anthropic / Claude ─────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "claude-opus-4-7")

    # ── Local models via Ollama ────────────────────────────────────────────────
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    LOCAL_MODEL: str = os.getenv("LOCAL_MODEL", "llama3.2")

    # ── Server ─────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── Agent loop ─────────────────────────────────────────────────────────────
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16000"))
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "30"))
    BASH_TIMEOUT: int = int(os.getenv("BASH_TIMEOUT", "30"))
    WEB_TIMEOUT: int = int(os.getenv("WEB_TIMEOUT", "15"))

    # ── Memory ─────────────────────────────────────────────────────────────────
    CHROMADB_PATH: str = os.getenv("CHROMADB_PATH", "./data/chromadb")


config = Config()

```

---

## `core/app.py`

```py
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
        code = 502 if "api_key" in str(e).lower() or "authentication" in str(e).lower() else 500
        return jsonify({"error": str(e), "status": "failed"}), code


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


# ── Models ───────────────────────────────────────────────────────────────────

@app.route("/api/models", methods=["GET"])
def models_list():
    from core.model_router import list_all_models
    return jsonify(list_all_models())


@app.route("/api/models/local", methods=["GET"])
def models_local():
    from core.local_models import list_models, is_available
    return jsonify({"available": is_available(), "models": list_models()})


@app.route("/api/models/pull", methods=["POST"])
def model_pull():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    def generate():
        from core.local_models import pull_model
        for line in pull_model(name):
            yield f"data: {line}\n\n"
        yield "event: done\ndata: pulled\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/models/delete", methods=["POST"])
def model_delete():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    from core.local_models import delete_model
    ok = delete_model(name)
    return jsonify({"deleted": ok, "name": name})


# ── Chat ─────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    history = data.get("history")
    session_id = request.headers.get("X-Session-Id", "default")
    model = data.get("model")  # optional — overrides default model
    from core.chat import chat
    reply = chat(message, session_id=session_id, history=history, model=model)
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


# ── Vision ───────────────────────────────────────────────────────────────────

@app.route("/api/vision/analyze", methods=["POST"])
def vision_analyze():
    from core.vision import VisionEngine
    engine = VisionEngine()
    if "image" in request.files:
        f = request.files["image"]
        question = request.form.get("question", "")
        data_bytes = f.read()
        mime = f.content_type or "image/jpeg"
        analysis = engine.analyze(data_bytes, mime, question)
    else:
        body = request.get_json(silent=True) or {}
        url = body.get("url", "").strip()
        question = body.get("question", "")
        if not url:
            return jsonify({"error": "Provide 'image' file or 'url' in JSON body"}), 400
        analysis = engine.analyze_from_url(url, question)
    return jsonify({"analysis": analysis})


@app.route("/api/vision/ocr", methods=["POST"])
def vision_ocr():
    if "image" not in request.files:
        return jsonify({"error": "image file required"}), 400
    f = request.files["image"]
    data = f.read()
    mime = f.content_type or "image/jpeg"
    from core.vision import VisionEngine
    text = VisionEngine().extract_text_ocr(data, mime)
    return jsonify({"text": text})


@app.route("/api/vision/compare", methods=["POST"])
def vision_compare():
    if "image1" not in request.files or "image2" not in request.files:
        return jsonify({"error": "image1 and image2 files required"}), 400
    f1, f2 = request.files["image1"], request.files["image2"]
    from core.vision import VisionEngine
    result = VisionEngine().compare_images(
        f1.read(), f1.content_type or "image/jpeg",
        f2.read(), f2.content_type or "image/jpeg",
    )
    return jsonify({"comparison": result})


# ── Data Analysis ─────────────────────────────────────────────────────────────

@app.route("/api/data/upload", methods=["POST"])
def data_upload():
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    f = request.files["file"]
    from core.data_analysis import DataAnalyst
    analyst = DataAnalyst()
    try:
        dataset = analyst.load_file(f)
        return jsonify({"summary": dataset.summary(), "columns": dataset.columns,
                        "rows": len(dataset.rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/data/analyze", methods=["POST"])
def data_analyze():
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    f = request.files["file"]
    question = request.form.get("question", "")
    from core.data_analysis import DataAnalyst
    analyst = DataAnalyst()
    try:
        dataset = analyst.load_file(f)
        answer = analyst.analyze(dataset, question)
        return jsonify({"answer": answer, "summary": dataset.summary()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/data/chart", methods=["POST"])
def data_chart():
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    f = request.files["file"]
    chart_type = request.form.get("chart_type", "auto")
    x_col = request.form.get("x_col", "")
    y_col = request.form.get("y_col", "")
    title = request.form.get("title", "")
    from core.data_analysis import DataAnalyst
    analyst = DataAnalyst()
    try:
        dataset = analyst.load_file(f)
        result = analyst.generate_chart(dataset, chart_type, x_col, y_col, title)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/charts/<chart_id>", methods=["GET"])
def serve_chart(chart_id: str):
    import re
    from flask import send_file
    if not re.fullmatch(r"[a-f0-9]{10}", chart_id):
        return jsonify({"error": "invalid chart id"}), 400
    path = os.path.join("data", "charts", f"chart_{chart_id}.png")
    if not os.path.exists(path):
        return jsonify({"error": "chart not found"}), 404
    return send_file(path, mimetype="image/png")


# ── Personas ──────────────────────────────────────────────────────────────────

@app.route("/api/personas", methods=["GET"])
def personas_list():
    from core.personas import list_personas
    return jsonify({"personas": list_personas()})


@app.route("/api/personas", methods=["POST"])
def persona_create():
    data = request.get_json(silent=True) or {}
    pid = data.get("id", "").strip()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    system = data.get("system", "").strip()
    emoji = data.get("emoji", "🤖")
    if not pid or not name or not system:
        return jsonify({"error": "id, name, and system are required"}), 400
    from core.personas import create_persona
    persona = create_persona(pid, name, description, system, emoji)
    return jsonify(persona), 201


@app.route("/api/personas/<persona_id>", methods=["GET"])
def persona_get(persona_id: str):
    from core.personas import get_persona
    p = get_persona(persona_id)
    if not p:
        return jsonify({"error": "persona not found"}), 404
    return jsonify(p)


@app.route("/api/personas/<persona_id>", methods=["DELETE"])
def persona_delete(persona_id: str):
    from core.personas import delete_persona
    ok = delete_persona(persona_id)
    if not ok:
        return jsonify({"error": "Cannot delete builtin persona or persona not found"}), 400
    return jsonify({"deleted": persona_id})


@app.route("/api/chat/persona", methods=["POST"])
def chat_with_persona():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    persona_id = data.get("persona_id", "default")
    if not message:
        return jsonify({"error": "message is required"}), 400
    session_id = request.headers.get("X-Session-Id", "default")
    model = data.get("model")
    from core.chat import chat
    from core.personas import get_system_prompt
    system = get_system_prompt(persona_id)
    reply = chat(
        message,
        session_id=f"{persona_id}:{session_id}",
        system_override=system,
        model=model,
    )
    return jsonify({"reply": reply, "persona_id": persona_id})


# ── Batch Tasks ───────────────────────────────────────────────────────────────

@app.route("/api/batch", methods=["POST"])
def batch_run():
    data = request.get_json(silent=True) or {}
    tasks = data.get("tasks", [])
    if not tasks or not isinstance(tasks, list):
        return jsonify({"error": "tasks (list) is required"}), 400
    if len(tasks) > 10:
        return jsonify({"error": "max 10 tasks per batch"}), 400
    from core.batch import run_batch
    result = run_batch([str(t) for t in tasks], max_workers=int(data.get("max_workers", 5)))
    return jsonify(result)


# ── Database ──────────────────────────────────────────────────────────────────

@app.route("/api/db/query", methods=["POST"])
def db_query():
    data = request.get_json(silent=True) or {}
    sql = data.get("sql", "").strip()
    if not sql:
        return jsonify({"error": "sql is required"}), 400
    from tools.db_tools import DBTools
    db = DBTools(data.get("db_url", ""))
    try:
        result = db.execute(sql, data.get("params"), data.get("db_path", "data/agent.db"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


@app.route("/api/db/tables", methods=["GET"])
def db_tables():
    from tools.db_tools import DBTools
    db = DBTools()
    tables = db.list_tables()
    return jsonify({"tables": tables})


@app.route("/api/db/describe/<table>", methods=["GET"])
def db_describe(table: str):
    from tools.db_tools import DBTools
    db = DBTools()
    return jsonify(db.describe_table(table))


# ── Browser Automation ────────────────────────────────────────────────────────

@app.route("/api/browser/screenshot", methods=["POST"])
def browser_screenshot():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    from tools.browser_tools import BrowserTools
    bt = BrowserTools()
    result = bt.screenshot(url, data.get("full_page", True))
    return jsonify(result)


@app.route("/api/browser/text", methods=["POST"])
def browser_text():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    from tools.browser_tools import BrowserTools
    text = BrowserTools().get_text(url)
    return jsonify({"text": text[:10000]})


@app.route("/api/browser/links", methods=["POST"])
def browser_links():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    from tools.browser_tools import BrowserTools
    links = BrowserTools().extract_links(url)
    return jsonify({"links": links})


@app.route("/api/screenshots/<shot_id>", methods=["GET"])
def serve_screenshot(shot_id: str):
    import re
    from flask import send_file
    if not re.fullmatch(r"[a-f0-9]{10}", shot_id):
        return jsonify({"error": "invalid id"}), 400
    path = os.path.join("data", "screenshots", f"shot_{shot_id}.png")
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="image/png")


# ── API Tester ────────────────────────────────────────────────────────────────

@app.route("/api/test/request", methods=["POST"])
def api_test_request():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    method = data.get("method", "GET")
    if not url:
        return jsonify({"error": "url is required"}), 400
    from tools.api_tester import APITester
    tester = APITester()
    response = tester.request(method, url, data.get("headers"), data.get("body"))
    try:
        analysis = tester.analyze_response(
            {"method": method, "url": url}, response, data.get("expectations", "")
        )
    except Exception as e:
        analysis = f"(AI analysis unavailable: {e})"
    return jsonify({"response": response, "analysis": analysis})


@app.route("/api/test/suite", methods=["POST"])
def api_test_suite():
    data = request.get_json(silent=True) or {}
    tests = data.get("tests", [])
    if not tests:
        return jsonify({"error": "tests list is required"}), 400
    from tools.api_tester import APITester
    results = APITester().run_test_suite(tests)
    passed = sum(1 for r in results if r["passed"])
    return jsonify({"total": len(results), "passed": passed,
                    "failed": len(results) - passed, "results": results})


# ── Docker ────────────────────────────────────────────────────────────────────

@app.route("/api/docker/<action>", methods=["POST"])
def docker_action(action: str):
    data = request.get_json(silent=True) or {}
    from tools.docker_tools import DockerTools
    dt = DockerTools()
    allowed = {
        "containers": lambda: dt.list_containers(data.get("all", False)),
        "images": lambda: dt.list_images(),
        "pull": lambda: dt.pull(data["image"]),
        "run": lambda: dt.run_container(
            data["image"], data.get("command", ""),
            data.get("ports"), data.get("env"),
            data.get("detach", True), data.get("remove", False),
        ),
        "stop": lambda: dt.stop(data["container_id"]),
        "remove": lambda: dt.remove(data["container_id"], data.get("force", False)),
        "logs": lambda: dt.logs(data["container_id"], data.get("tail", 100)),
        "stats": lambda: dt.stats(data["container_id"]),
        "exec": lambda: dt.exec_cmd(data["container_id"], data["command"]),
        "inspect": lambda: dt.inspect(data["container_id"]),
    }
    if action not in allowed:
        return jsonify({"error": f"Unknown action '{action}'"}), 400
    try:
        result = allowed[action]()
        return jsonify(result)
    except KeyError as e:
        return jsonify({"error": f"Missing parameter: {e}"}), 400


# ── Monitoring ────────────────────────────────────────────────────────────────

@app.route("/api/monitoring/stats", methods=["GET"])
def monitoring_stats():
    from core.monitoring import get_stats
    return jsonify(get_stats())


@app.route("/api/monitoring/requests", methods=["GET"])
def monitoring_requests():
    n = int(request.args.get("n", 50))
    from core.monitoring import get_recent_requests
    return jsonify({"requests": get_recent_requests(n)})


@app.route("/api/monitoring/hourly", methods=["GET"])
def monitoring_hourly():
    from core.monitoring import get_hourly_summary
    return jsonify({"hourly": get_hourly_summary()})


# ── Prompt Templates ──────────────────────────────────────────────────────────

@app.route("/api/templates", methods=["GET"])
def templates_list():
    from core.prompt_templates import list_templates
    return jsonify({"templates": list_templates()})


@app.route("/api/templates", methods=["POST"])
def template_create():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    template = data.get("template", "").strip()
    if not name or not template:
        return jsonify({"error": "name and template are required"}), 400
    from core.prompt_templates import create_template
    rec = create_template(name, template, data.get("description", ""),
                           data.get("id"))
    return jsonify(rec), 201


@app.route("/api/templates/<template_id>", methods=["GET"])
def template_get(template_id: str):
    from core.prompt_templates import get_template
    t = get_template(template_id)
    if not t:
        return jsonify({"error": "template not found"}), 404
    return jsonify(t)


@app.route("/api/templates/<template_id>", methods=["DELETE"])
def template_delete(template_id: str):
    from core.prompt_templates import delete_template
    ok = delete_template(template_id)
    if not ok:
        return jsonify({"error": "Cannot delete builtin template or not found"}), 400
    return jsonify({"deleted": template_id})


@app.route("/api/templates/<template_id>/render", methods=["POST"])
def template_render(template_id: str):
    data = request.get_json(silent=True) or {}
    variables = data.get("variables", {})
    from core.prompt_templates import render_template
    try:
        rendered = render_template(template_id, variables)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"rendered": rendered})


@app.route("/api/templates/<template_id>/run", methods=["POST"])
def template_run(template_id: str):
    data = request.get_json(silent=True) or {}
    variables = data.get("variables", {})
    from core.prompt_templates import render_template
    try:
        prompt = render_template(template_id, variables)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    from core.orchestrator import AIOrchestrator
    output = AIOrchestrator().run_task_sync(prompt)
    return jsonify({"output": output, "prompt": prompt})


# ── Slack / Discord ───────────────────────────────────────────────────────────

@app.route("/api/notify/slack", methods=["POST"])
def notify_slack():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    from core.integrations import send_slack_message
    result = send_slack_message(text, data.get("channel", ""),
                                 data.get("webhook_url", ""))
    return jsonify(result)


@app.route("/api/notify/discord", methods=["POST"])
def notify_discord():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    from core.integrations import send_discord_message
    result = send_discord_message(text, data.get("webhook_url", ""),
                                   data.get("username", "AI Agent"))
    return jsonify(result)


@app.route("/api/notify/all", methods=["POST"])
def notify_all():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    from core.integrations import notify
    result = notify(message, data.get("channels"))
    return jsonify(result)


# ── Multi-Agent System ────────────────────────────────────────────────────────

@app.route("/api/agents", methods=["GET"])
def agents_list():
    from agents.coordinator import get_coordinator
    return jsonify({"agents": get_coordinator().get_agents_info()})


@app.route("/api/agents/run", methods=["POST"])
def agents_run():
    data = request.get_json(silent=True) or {}
    task = data.get("task", "").strip()
    mode = data.get("mode", "auto")   # auto | debate | parallel
    if not task:
        return jsonify({"error": "task is required"}), 400
    if mode not in ("auto", "debate", "parallel"):
        return jsonify({"error": "mode must be auto, debate, or parallel"}), 400
    from agents.coordinator import get_coordinator
    try:
        result = get_coordinator().run(task, mode=mode)
        return jsonify(result)
    except Exception as e:
        logger.exception("Multi-agent run failed")
        code = 502 if "api_key" in str(e).lower() or "authentication" in str(e).lower() else 500
        return jsonify({"error": str(e)}), code


@app.route("/api/agents/stream", methods=["POST"])
def agents_stream():
    data = request.get_json(silent=True) or {}
    task = data.get("task", "").strip()
    mode = data.get("mode", "auto")
    if not task:
        return jsonify({"error": "task is required"}), 400

    def generate():
        from agents.coordinator import get_coordinator
        try:
            for chunk in get_coordinator().stream_run(task, mode=mode):
                escaped = chunk.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"
        except Exception as e:
            yield f"data: [error: {e}]\n\n"
        yield "event: done\ndata: completed\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/agents/history", methods=["GET"])
def agents_history():
    from agents.coordinator import get_coordinator
    return jsonify({"history": get_coordinator().get_history()})


# ── System Resources & Desktop Notifications ──────────────────────────────────

@app.route("/api/system/resources", methods=["GET"])
def system_resources():
    from tools.notify_tools import get_system_resources
    return jsonify(get_system_resources())


@app.route("/api/system/check", methods=["GET"])
def system_check():
    from tools.notify_tools import check_and_alert
    return jsonify(check_and_alert())


@app.route("/api/system/notify", methods=["POST"])
def system_notify():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "AI Agent").strip()
    body = data.get("body", "").strip()
    urgency = data.get("urgency", "normal")
    if not body:
        return jsonify({"error": "body is required"}), 400
    from tools.notify_tools import send_notification
    sent = send_notification(title, body, urgency=urgency)
    return jsonify({"sent": sent, "title": title, "body": body})


@app.route("/api/system/monitor", methods=["GET"])
def system_monitor_status():
    from tools.notify_tools import monitor_status
    return jsonify(monitor_status())


@app.route("/api/system/monitor/start", methods=["POST"])
def system_monitor_start():
    data = request.get_json(silent=True) or {}
    interval = int(data.get("interval_s", 60))
    from tools.notify_tools import start_monitor
    started = start_monitor(interval_s=interval)
    return jsonify({"started": started, "interval_s": interval})


@app.route("/api/system/monitor/stop", methods=["POST"])
def system_monitor_stop():
    from tools.notify_tools import stop_monitor
    stopped = stop_monitor()
    return jsonify({"stopped": stopped})


# ── Automation: Morning Briefing & Maintenance ────────────────────────────────

@app.route("/api/automation/briefing", methods=["GET", "POST"])
def automation_briefing():
    data = request.get_json(silent=True) or {}
    note = data.get("note", "") if request.method == "POST" else ""
    try:
        from automation.briefing import generate_briefing
        result = generate_briefing(custom_note=note)
        return jsonify(result)
    except Exception as e:
        logger.exception("Briefing generation failed")
        code = 502 if "api_key" in str(e).lower() or "authentication" in str(e).lower() else 500
        return jsonify({"error": str(e)}), code


@app.route("/api/automation/maintenance", methods=["POST"])
def automation_maintenance():
    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))
    action = data.get("action", "all")   # all | temp | logs | disk
    try:
        from automation.maintenance import (
            clean_temp_files, clean_old_logs, disk_report, run_all_maintenance
        )
        if action == "temp":
            result = clean_temp_files(dry_run=dry_run)
        elif action == "logs":
            result = clean_old_logs(dry_run=dry_run)
        elif action == "disk":
            result = disk_report()
        else:
            result = run_all_maintenance(dry_run=dry_run)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Voice Interface (Whisper STT) ─────────────────────────────────────────────

@app.route("/api/voice/status", methods=["GET"])
def voice_status():
    from tools.voice_tools import whisper_available, get_available_models
    return jsonify({
        "whisper_available": whisper_available(),
        "models": get_available_models(),
    })


@app.route("/api/voice/transcribe", methods=["POST"])
def voice_transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "audio file required"}), 400
    f = request.files["audio"]
    language = request.form.get("language") or None
    model_size = request.form.get("model", "base")
    ext = "." + (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "wav")

    try:
        from tools.voice_tools import transcribe_bytes
        result = transcribe_bytes(f.read(), ext=ext, language=language, model_size=model_size)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        logger.exception("Transcription failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/voice/transcribe-and-run", methods=["POST"])
def voice_transcribe_and_run():
    """Transcribe audio then execute as an agent task."""
    if "audio" not in request.files:
        return jsonify({"error": "audio file required"}), 400
    f = request.files["audio"]
    model_size = request.form.get("model", "base")
    ext = "." + (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "wav")

    try:
        from tools.voice_tools import transcribe_bytes
        transcription = transcribe_bytes(f.read(), ext=ext, model_size=model_size)
        text = transcription.get("text", "").strip()
        if not text:
            return jsonify({"error": "No speech detected", "transcription": transcription}), 400

        from core.orchestrator import AIOrchestrator
        output = AIOrchestrator().run_task_sync(text)
        return jsonify({
            "transcription": transcription,
            "task": text,
            "output": output,
        })
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        logger.exception("Voice task failed")
        return jsonify({"error": str(e)}), 500


# ── Self-Healing System ───────────────────────────────────────────────────────

@app.route("/api/heal/analyze", methods=["POST"])
def heal_analyze():
    data = request.get_json(silent=True) or {}
    error = data.get("error", "").strip()
    task = data.get("task", "").strip()
    file_hint = data.get("file", "").strip()
    if not error:
        return jsonify({"error": "error field is required"}), 400
    from core.self_healer import get_healer
    patch = get_healer().analyze(error, task=task, file_hint=file_hint)
    return jsonify(patch)


@app.route("/api/heal/apply", methods=["POST"])
def heal_apply():
    data = request.get_json(silent=True) or {}
    patch = data.get("patch")
    if not patch:
        return jsonify({"error": "patch object is required"}), 400
    from core.self_healer import get_healer
    result = get_healer().apply(patch)
    return jsonify(result)


@app.route("/api/heal/auto", methods=["POST"])
def heal_auto():
    """Analyze + apply in one call."""
    data = request.get_json(silent=True) or {}
    error = data.get("error", "").strip()
    task = data.get("task", "").strip()
    if not error:
        return jsonify({"error": "error field is required"}), 400
    from core.self_healer import auto_heal
    result = auto_heal(error, task=task)
    return jsonify(result)


@app.route("/api/heal/log", methods=["GET"])
def heal_log():
    from core.self_healer import get_healer
    return jsonify({"log": get_healer().get_log()})


@app.route("/api/heal/backups", methods=["GET"])
def heal_backups():
    from core.self_healer import get_healer
    return jsonify({"backups": get_healer().list_backups()})


@app.route("/api/heal/restore", methods=["POST"])
def heal_restore():
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "").strip()
    if not backup_path:
        return jsonify({"error": "backup_path is required"}), 400
    from core.self_healer import get_healer
    ok = get_healer().restore(backup_path)
    return jsonify({"restored": ok, "backup_path": backup_path})


# ── Digital Twin ──────────────────────────────────────────────────────────────

@app.route("/api/twin/profile", methods=["GET"])
def twin_profile():
    from agents.digital_twin import get_twin
    twin = get_twin()
    return jsonify({"profile": twin.get_profile(), "summary": twin.get_summary()})


@app.route("/api/twin/ingest/code", methods=["POST"])
def twin_ingest_code():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400
    from agents.digital_twin import get_twin
    result = get_twin().ingest_code(code, filename=data.get("filename", ""),
                                     language=data.get("language", "python"))
    return jsonify(result)


@app.route("/api/twin/ingest/file", methods=["POST"])
def twin_ingest_file():
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    f = request.files["file"]
    content = f.read().decode("utf-8", errors="ignore")
    ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else "txt"
    lang = {"py": "python", "md": "markdown", "js": "javascript"}.get(ext, "text")
    from agents.digital_twin import get_twin
    result = get_twin().ingest_code(content, filename=f.filename, language=lang)
    return jsonify(result)


@app.route("/api/twin/ingest/directory", methods=["POST"])
def twin_ingest_directory():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path is required"}), 400
    from agents.digital_twin import get_twin
    result = get_twin().ingest_directory(path)
    return jsonify(result)


@app.route("/api/twin/ask", methods=["POST"])
def twin_ask():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    from agents.digital_twin import get_twin
    reply = get_twin().respond(question)
    return jsonify({"reply": reply})


@app.route("/api/twin/ask/stream", methods=["POST"])
def twin_ask_stream():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    def generate():
        from agents.digital_twin import get_twin
        try:
            for chunk in get_twin().respond(question, stream=True):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: [error: {e}]\n\n"
        yield "event: done\ndata: \n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/twin/probe", methods=["GET"])
def twin_probe():
    from agents.digital_twin import get_twin
    question = get_twin().generate_probing_question()
    return jsonify({"question": question})


@app.route("/api/twin/probe/answer", methods=["POST"])
def twin_probe_answer():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()
    if not question or not answer:
        return jsonify({"error": "question and answer are required"}), 400
    from agents.digital_twin import get_twin
    get_twin().record_answer(question, answer)
    return jsonify({"recorded": True})


@app.route("/api/twin/name", methods=["POST"])
def twin_set_name():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    from agents.digital_twin import get_twin
    get_twin().update_name(name)
    return jsonify({"name": name})


@app.route("/api/twin/log", methods=["GET"])
def twin_log():
    from agents.digital_twin import get_twin
    return jsonify({"log": get_twin().get_ingestion_log()})


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)

```

---

## `core/orchestrator.py`

```py
import json
import logging
from collections.abc import Generator

import anthropic

from core.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a powerful AI agent capable of completing complex tasks autonomously.

You have access to these tools:
- **execute_bash**: Run bash commands (files, packages, scripts, system ops)
- **read_file**: Read any file's contents
- **write_file**: Write or append content to files
- **search_files**: Find files matching a glob pattern
- **web_fetch**: Fetch and extract content from a URL
- **memory_store**: Persist information for future sessions
- **memory_search**: Semantic search over stored memories

How to approach tasks:
1. Break complex tasks into concrete steps
2. Use tools proactively — gather info before acting
3. Verify results after each important step
4. Store key findings in memory for reuse
5. Report progress clearly with what you did and what you found

Safety rules: never delete system files, never expose secrets, confirm before irreversible operations."""


def _build_tool_definitions() -> list[dict]:
    return [
        {
            "name": "execute_bash",
            "description": "Execute a bash command and return stdout/stderr. Use for filesystem ops, running scripts, installing packages, checking system info.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
        {
            "name": "read_file",
            "description": "Read the contents of a file from disk.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"}
                },
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Write or append content to a file. Creates parent directories automatically.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "Content to write"},
                    "mode": {
                        "type": "string",
                        "enum": ["w", "a"],
                        "description": "w=overwrite (default), a=append",
                        "default": "w",
                    },
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "search_files",
            "description": "Search for files matching a glob pattern in a directory.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py'",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search (default: current)",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "web_fetch",
            "description": "Fetch a URL and return its text content. Good for documentation, APIs, web scraping.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "extract": {
                        "type": "string",
                        "enum": ["text", "links", "html"],
                        "description": "What to extract: text (default), links, or raw html",
                        "default": "text",
                    },
                },
                "required": ["url"],
            },
        },
        {
            "name": "memory_store",
            "description": "Store a piece of information persistently so it can be recalled later via memory_search.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Unique identifier for this memory",
                    },
                    "content": {"type": "string", "description": "Information to remember"},
                    "metadata": {
                        "type": "object",
                        "description": "Optional tags or labels",
                    },
                },
                "required": ["key", "content"],
            },
        },
        {
            "name": "memory_search",
            "description": "Search stored memories using semantic similarity.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "n_results": {
                        "type": "integer",
                        "description": "How many results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "send_email",
            "description": "Send an email notification. Requires SMTP config in environment.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                },
                "required": ["to", "subject", "body"],
            },
        },
        {
            "name": "github",
            "description": "Interact with GitHub: read repos/files/issues/PRs, create issues, search code.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_repo", "list_repos", "get_file", "list_files",
                                 "list_issues", "create_issue", "comment_on_issue",
                                 "list_prs", "create_pr", "search_code"],
                        "description": "GitHub action to perform",
                    },
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "path": {"type": "string", "description": "File path in repo"},
                    "title": {"type": "string", "description": "Issue/PR title"},
                    "body": {"type": "string", "description": "Issue/PR body"},
                    "head": {"type": "string", "description": "PR head branch"},
                    "base": {"type": "string", "description": "PR base branch"},
                    "number": {"type": "integer", "description": "Issue/PR number"},
                    "query": {"type": "string", "description": "Search query"},
                    "username": {"type": "string", "description": "GitHub username"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                    "comment": {"type": "string", "description": "Comment text"},
                },
                "required": ["action"],
            },
        },
        {
            "name": "execute_python",
            "description": "Execute Python code in a safe sandbox and return stdout/stderr. Great for calculations, data processing, generating charts, etc.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 15)",
                        "default": 15,
                    },
                },
                "required": ["code"],
            },
        },
    ]


class AIOrchestrator:
    def __init__(self):
        self.tools = _build_tool_definitions()
        self._os_tools = None
        self._web_tools = None
        self._file_tools = None
        self._memory = None

    # Lazy-load tools to avoid circular imports and heavy init at startup
    @property
    def os_tools(self):
        if self._os_tools is None:
            from tools.os_tools import OSTools
            self._os_tools = OSTools()
        return self._os_tools

    @property
    def web_tools(self):
        if self._web_tools is None:
            from tools.web_tools import WebTools
            self._web_tools = WebTools()
        return self._web_tools

    @property
    def file_tools(self):
        if self._file_tools is None:
            from tools.file_tools import FileTools
            self._file_tools = FileTools()
        return self._file_tools

    @property
    def memory(self):
        if self._memory is None:
            from memory.memory_manager import MemoryManager
            self._memory = MemoryManager(config.CHROMADB_PATH)
        return self._memory

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        try:
            if name == "execute_bash":
                return self.os_tools.execute_bash(
                    inputs["command"], inputs.get("timeout", config.BASH_TIMEOUT)
                )
            if name == "read_file":
                return self.file_tools.read_file(inputs["path"])
            if name == "write_file":
                return self.file_tools.write_file(
                    inputs["path"], inputs["content"], inputs.get("mode", "w")
                )
            if name == "search_files":
                return self.file_tools.search_files(
                    inputs["pattern"], inputs.get("directory", ".")
                )
            if name == "web_fetch":
                return self.web_tools.fetch(inputs["url"], inputs.get("extract", "text"))
            if name == "memory_store":
                self.memory.store(
                    inputs["key"], inputs["content"], inputs.get("metadata", {})
                )
                return f"Stored: {inputs['key']}"
            if name == "memory_search":
                results = self.memory.search(inputs["query"], inputs.get("n_results", 5))
                return json.dumps(results, ensure_ascii=False, indent=2)
            if name == "send_email":
                from core.notifications import send_email
                return send_email(inputs["to"], inputs["subject"], inputs["body"])
            if name == "github":
                from tools.github_tools import GitHubTools
                gh = GitHubTools()
                action = inputs.pop("action")
                return gh.dispatch(action, **inputs)
            if name == "execute_python":
                from tools.code_sandbox import CodeSandbox
                sandbox = CodeSandbox()
                result = sandbox.execute(inputs["code"], inputs.get("timeout", 15))
                return sandbox.format_result(result)
            return f"Unknown tool: {name}"
        except Exception as exc:
            logger.warning("Tool %s raised: %s", name, exc)
            return f"Error in {name}: {exc}"

    def run_task(self, task: str) -> Generator[str, None, None]:
        """Run a task and yield text chunks as they become available."""
        from core import model_router
        messages: list[dict] = [{"role": "user", "content": task}]
        model = config.MODEL

        for iteration in range(config.MAX_AGENT_ITERATIONS):
            response = model_router.chat_with_tools(
                messages,
                self.tools,
                model=model,
                system=SYSTEM_PROMPT,
            )

            if response["text"]:
                yield response["text"]

            if response["stop_reason"] == "end_turn":
                break

            if response["stop_reason"] != "tool_use":
                logger.warning("Unexpected stop_reason: %s", response["stop_reason"])
                break

            # Add assistant turn to history
            messages.append(response["_history_assistant"])

            # Execute tool calls
            tool_results = []
            for tc in response["tool_calls"]:
                preview = json.dumps(tc["inputs"], ensure_ascii=False)[:120]
                yield f"\n\n**[{tc['name']}]** `{preview}`\n"
                result = self._dispatch_tool(tc["name"], tc["inputs"])
                tool_results.append({"id": tc["id"], "result": result})

            # Add tool results in the right backend format
            messages.extend(model_router.build_tool_result_messages(tool_results, model))

            if iteration == config.MAX_AGENT_ITERATIONS - 1:
                yield "\n\n[Max iterations reached]"

    def run_task_sync(self, task: str) -> str:
        return "".join(self.run_task(task))

```

---

## `core/chat.py`

```py
"""Multi-turn chat — maintains per-session history and routes to Claude or Ollama."""

import logging
import threading

from core.config import config

logger = logging.getLogger(__name__)

_CHAT_SYSTEM = """You are a helpful, smart AI assistant. You can answer questions, help with coding,
writing, analysis, and complex reasoning. Respond in the same language the user writes in.
Be concise but thorough. Format responses with markdown when it helps clarity."""

_sessions: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _get_or_create(session_id: str) -> list[dict]:
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = []
        return _sessions[session_id]


def chat(
    message: str,
    session_id: str = "default",
    history: list[dict] | None = None,
    system_override: str | None = None,
    model: str | None = None,
) -> str:
    """
    Send a message and get a reply.

    Args:
        message: The user message.
        session_id: Identifies the conversation session (history is kept per session).
        history: Explicit history list — if provided, session history is ignored.
        system_override: Override the default system prompt (used by personas).
        model: Model to use. Defaults to config.MODEL. Pass an Ollama model name
               (e.g. "llama3.2") to use a local model instead of Claude.

    Returns:
        The assistant reply as a string.
    """
    from core.model_router import chat as route_chat

    if history is not None:
        messages = [m for m in history if m.get("role") in ("user", "assistant")]
        messages.append({"role": "user", "content": message})
    else:
        messages = _get_or_create(session_id)
        messages.append({"role": "user", "content": message})

    system = system_override or _CHAT_SYSTEM
    model = model or config.MODEL

    try:
        reply = route_chat(messages[-40:], model=model, system=system)
        if isinstance(reply, str):
            pass
        else:
            reply = "".join(reply)

        if history is None:
            with _lock:
                messages.append({"role": "assistant", "content": reply})

        return reply
    except Exception as exc:
        logger.exception("Chat error")
        return f"Error: {exc}"


def clear_session(session_id: str = "default") -> None:
    with _lock:
        _sessions.pop(session_id, None)


def get_sessions() -> list[str]:
    with _lock:
        return list(_sessions.keys())

```

---

## `core/model_router.py`

```py
"""Model Router — unified interface for Claude (Anthropic) and local models (Ollama)."""

import logging
from typing import Iterator

import anthropic

from core.config import config

logger = logging.getLogger(__name__)

# Any model name starting with these prefixes is treated as a Claude model
_CLAUDE_PREFIXES = ("claude-",)

_CHAT_SYSTEM = """You are a helpful, smart AI assistant. You can answer questions, help with coding,
writing, analysis, and complex reasoning. Respond in the same language the user writes in.
Be concise but thorough. Format responses with markdown when it helps clarity."""


def is_claude(model: str) -> bool:
    return any(model.startswith(p) for p in _CLAUDE_PREFIXES)


def is_local(model: str) -> bool:
    return not is_claude(model)


def chat(
    messages: list[dict],
    model: str | None = None,
    system: str = "",
    max_tokens: int | None = None,
    stream: bool = False,
) -> str | Iterator[str]:
    """
    Route a chat request to the appropriate backend.

    Args:
        messages: List of {role, content} dicts.
        model: Model identifier. If None, uses config.MODEL.
        system: System prompt override.
        max_tokens: Max tokens. Defaults to config.MAX_TOKENS.
        stream: Stream output as chunks.

    Returns:
        Full reply string, or generator of chunks when stream=True.
    """
    model = model or config.MODEL
    max_tokens = max_tokens or config.MAX_TOKENS
    system = system or _CHAT_SYSTEM

    if is_claude(model):
        return _claude_chat(messages, model, system, max_tokens, stream)
    return _ollama_chat(messages, model, system, max_tokens, stream)


# ── Claude ────────────────────────────────────────────────────────────────────

def _claude_chat(
    messages: list[dict],
    model: str,
    system: str,
    max_tokens: int,
    stream: bool,
) -> str | Iterator[str]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages[-40:],
    )
    # Adaptive thinking only on models that support it
    if model.startswith("claude-opus") or model.startswith("claude-sonnet"):
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        if stream:
            return _claude_stream(client, kwargs)
        resp = client.messages.create(**kwargs)
        return next((b.text for b in resp.content if b.type == "text"), "")
    except Exception as exc:
        logger.exception("Claude chat error")
        return f"Claude error: {exc}"


def _claude_stream(client, kwargs) -> Iterator[str]:
    try:
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:
        yield f"Claude stream error: {exc}"


# ── Ollama ────────────────────────────────────────────────────────────────────

def _ollama_chat(
    messages: list[dict],
    model: str,
    system: str,
    max_tokens: int,
    stream: bool,
) -> str | Iterator[str]:
    from core.local_models import chat as ollama_chat
    return ollama_chat(messages, model=model, system=system, max_tokens=max_tokens, stream=stream)


# ── Generate (single-turn) ────────────────────────────────────────────────────

def generate(prompt: str, model: str | None = None, system: str = "") -> str:
    """Single-turn text generation routed to Claude or Ollama."""
    model = model or config.MODEL
    if is_claude(model):
        messages = [{"role": "user", "content": prompt}]
        result = _claude_chat(messages, model, system, config.MAX_TOKENS, False)
        return result if isinstance(result, str) else "".join(result)
    from core.local_models import generate as ollama_gen
    return ollama_gen(prompt, model=model, system=system)


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
    system: str = "",
    max_tokens: int | None = None,
) -> dict:
    """
    Route a tool-use chat to Claude or Ollama.

    Returns normalized dict:
      text, tool_calls, stop_reason, _history_assistant, _backend
    """
    model = model or config.MODEL
    max_tokens = max_tokens or config.MAX_TOKENS
    system = system or _CHAT_SYSTEM

    if is_claude(model):
        return _claude_chat_with_tools(messages, tools, model, system, max_tokens)
    return _ollama_chat_with_tools(messages, tools, model, system, max_tokens)


def _claude_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    system: str,
    max_tokens: int,
) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        tools=tools,
        messages=messages[-40:],
    )
    if model.startswith("claude-opus") or model.startswith("claude-sonnet"):
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()

        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "inputs": block.input})

        return {
            "text": text,
            "tool_calls": tool_calls,
            "stop_reason": response.stop_reason,
            "_history_assistant": {"role": "assistant", "content": response.content},
            "_backend": "claude",
        }
    except Exception as exc:
        logger.exception("Claude tool-use error")
        return {
            "text": f"Claude error: {exc}",
            "tool_calls": [],
            "stop_reason": "end_turn",
            "_history_assistant": {"role": "assistant", "content": f"Error: {exc}"},
            "_backend": "claude",
        }


def _ollama_chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str,
    system: str,
    max_tokens: int,
) -> dict:
    from core.local_models import chat_with_tools as ollama_cwt
    return ollama_cwt(messages, tools, model=model, system=system, max_tokens=max_tokens)


def build_tool_result_messages(
    tool_results: list[dict],
    model: str | None = None,
) -> list[dict]:
    """
    Build the tool-result messages for the right backend.
    tool_results: [{"id": str, "result": str}]
    Returns list of message dicts to extend the conversation.
    """
    model = model or config.MODEL
    if is_claude(model):
        return [{
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tr["id"], "content": tr["result"]}
                for tr in tool_results
            ],
        }]
    # Ollama: one "tool" role message per result
    return [{"role": "tool", "content": tr["result"]} for tr in tool_results]


def list_all_models() -> dict:
    """Return all available models: Claude (static list) + local Ollama models."""
    claude_models = [
        {"id": "claude-opus-4-7",    "name": "Claude Opus 4.7",    "provider": "anthropic", "recommended": True},
        {"id": "claude-sonnet-4-6",  "name": "Claude Sonnet 4.6",  "provider": "anthropic", "recommended": True},
        {"id": "claude-haiku-4-5",   "name": "Claude Haiku 4.5",   "provider": "anthropic", "recommended": False},
    ]
    from core.local_models import list_models, is_available
    local_available = is_available()
    local_models = []
    if local_available:
        for m in list_models():
            name = m.get("name") or m.get("model", "")
            local_models.append({
                "id": name,
                "name": name,
                "provider": "ollama",
                "size": m.get("size", 0),
                "recommended": any(name.startswith(r) for r in ("llama3", "mistral", "qwen", "deepseek")),
            })
    return {
        "claude": claude_models,
        "local": local_models,
        "ollama_available": local_available,
        "current_model": config.MODEL,
    }

```

---

## `core/local_models.py`

```py
"""Local model support via Ollama — run LLMs fully offline."""

import json
import logging
from typing import Iterator

import requests

from core.config import config

logger = logging.getLogger(__name__)

_OLLAMA_BASE = config.OLLAMA_URL.rstrip("/")

# Models known to support tool use / structured output well
RECOMMENDED_MODELS = [
    "llama3.2",
    "llama3.1",
    "mistral",
    "mixtral",
    "qwen2.5",
    "qwen2.5-coder",
    "codellama",
    "deepseek-r1",
    "phi4",
    "gemma2",
]


def is_available() -> bool:
    """Return True if Ollama is reachable."""
    try:
        r = requests.get(f"{_OLLAMA_BASE}/api/tags", timeout=3)
        return r.ok
    except Exception:
        return False


def list_models() -> list[dict]:
    """Return all locally pulled Ollama models."""
    try:
        r = requests.get(f"{_OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        return r.json().get("models", [])
    except Exception as exc:
        logger.warning("Ollama list_models failed: %s", exc)
        return []


def pull_model(model_name: str) -> Iterator[str]:
    """Stream pull progress for a model. Yields status lines."""
    try:
        with requests.post(
            f"{_OLLAMA_BASE}/api/pull",
            json={"name": model_name},
            stream=True,
            timeout=600,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        status = data.get("status", "")
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)
                        if total:
                            pct = round(completed / total * 100)
                            yield f"{status} — {pct}%"
                        else:
                            yield status
                    except json.JSONDecodeError:
                        yield line.decode() if isinstance(line, bytes) else line
    except Exception as exc:
        yield f"Error: {exc}"


def delete_model(model_name: str) -> bool:
    """Delete a locally pulled model."""
    try:
        r = requests.delete(
            f"{_OLLAMA_BASE}/api/delete",
            json={"name": model_name},
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def chat(
    messages: list[dict],
    model: str | None = None,
    system: str = "",
    max_tokens: int = 4096,
    stream: bool = False,
) -> str | Iterator[str]:
    """
    Chat with an Ollama model.

    Args:
        messages: List of {role, content} dicts (same format as Anthropic).
        model: Ollama model name. Falls back to config.LOCAL_MODEL.
        system: Optional system prompt.
        max_tokens: Maximum tokens to generate.
        stream: If True, returns a generator yielding text chunks.

    Returns:
        Full reply string, or a generator of chunks if stream=True.
    """
    model = model or config.LOCAL_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"num_predict": max_tokens},
    }
    if system:
        payload["system"] = system

    try:
        if stream:
            return _stream_chat(payload)
        resp = requests.post(
            f"{_OLLAMA_BASE}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as exc:
        logger.exception("Ollama chat error")
        return f"Ollama error: {exc}"


def _stream_chat(payload: dict) -> Iterator[str]:
    try:
        with requests.post(
            f"{_OLLAMA_BASE}/api/chat",
            json={**payload, "stream": True},
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        yield f"Ollama stream error: {exc}"


def generate(
    prompt: str,
    model: str | None = None,
    system: str = "",
    max_tokens: int = 4096,
) -> str:
    """Single-turn generation (no history)."""
    model = model or config.LOCAL_MODEL
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if system:
        payload["system"] = system
    try:
        resp = requests.post(
            f"{_OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as exc:
        return f"Ollama error: {exc}"


def _anthropic_tools_to_ollama(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to Ollama/OpenAI function-call format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
    system: str = "",
    max_tokens: int = 4096,
) -> dict:
    """
    Chat with Ollama using tool use.

    Returns normalized dict:
      text, tool_calls, stop_reason, _history_assistant, _backend
    """
    model = model or config.LOCAL_MODEL
    ollama_tools = _anthropic_tools_to_ollama(tools)

    ollama_messages: list[dict] = []
    if system:
        ollama_messages.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, list):
            # Tool results or mixed content blocks
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    ollama_messages.append({"role": "tool", "content": block.get("content", "")})
                elif isinstance(block, dict) and block.get("type") == "text":
                    ollama_messages.append({"role": role, "content": block.get("text", "")})
                # Skip thinking blocks
        elif msg.get("tool_calls"):
            # Already an Ollama-format assistant message with tool_calls
            ollama_messages.append(msg)
        else:
            ollama_messages.append({"role": role, "content": content})

    payload = {
        "model": model,
        "messages": ollama_messages,
        "tools": ollama_tools,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }

    try:
        resp = requests.post(f"{_OLLAMA_BASE}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})
        text = message.get("content", "") or ""
        tool_calls_raw = message.get("tool_calls") or []

        tool_calls = []
        for i, tc in enumerate(tool_calls_raw):
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_calls.append({
                "id": f"call_{i}_{fn.get('name', '')}",
                "name": fn.get("name", ""),
                "inputs": args,
            })

        stop_reason = "tool_use" if tool_calls else "end_turn"
        history_assistant: dict = {"role": "assistant", "content": text}
        if tool_calls:
            history_assistant["tool_calls"] = [
                {"function": {"name": tc["name"], "arguments": tc["inputs"]}}
                for tc in tool_calls
            ]

        return {
            "text": text,
            "tool_calls": tool_calls,
            "stop_reason": stop_reason,
            "_history_assistant": history_assistant,
            "_backend": "ollama",
        }
    except Exception as exc:
        logger.exception("Ollama chat_with_tools error")
        return {
            "text": f"Ollama error: {exc}",
            "tool_calls": [],
            "stop_reason": "end_turn",
            "_history_assistant": {"role": "assistant", "content": f"Error: {exc}"},
            "_backend": "ollama",
        }


def model_info(model_name: str) -> dict:
    """Return model metadata."""
    try:
        r = requests.post(
            f"{_OLLAMA_BASE}/api/show",
            json={"name": model_name},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}

```

---

## `core/personas.py`

```py
"""Agent Personas — specialized personalities for different use cases."""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

_BUILTIN_PERSONAS: dict[str, dict] = {
    "default": {
        "id": "default",
        "name": "AI Agent",
        "description": "General-purpose AI agent for any task",
        "system": "You are a powerful AI agent. Be helpful, accurate, and thorough.",
        "emoji": "🤖",
        "builtin": True,
    },
    "developer": {
        "id": "developer",
        "name": "Senior Developer",
        "description": "Expert software engineer specializing in clean code and problem solving",
        "system": (
            "You are a senior software engineer with 15+ years of experience. "
            "You write clean, efficient, well-documented code. You explain technical "
            "concepts clearly, suggest best practices, review code critically, and "
            "provide working solutions. You prefer Python, TypeScript, and modern tools."
        ),
        "emoji": "👨‍💻",
        "builtin": True,
    },
    "analyst": {
        "id": "analyst",
        "name": "Data Analyst",
        "description": "Expert in statistics, data analysis, and visualizations",
        "system": (
            "You are an expert data analyst and scientist. You excel at interpreting data, "
            "finding patterns, building models, creating visualizations, and communicating "
            "insights clearly. You know Python (pandas, numpy, matplotlib, sklearn), SQL, "
            "and statistical methods deeply."
        ),
        "emoji": "📊",
        "builtin": True,
    },
    "writer": {
        "id": "writer",
        "name": "Creative Writer",
        "description": "Talented writer specializing in content, stories, and marketing copy",
        "system": (
            "You are a talented creative writer and content strategist. You craft compelling "
            "narratives, engaging blog posts, persuasive copy, and creative stories. "
            "You adapt your tone and style to the audience and purpose. "
            "You understand SEO, storytelling, and brand voice."
        ),
        "emoji": "✍️",
        "builtin": True,
    },
    "researcher": {
        "id": "researcher",
        "name": "Research Analyst",
        "description": "Meticulous researcher who gathers and synthesizes information in depth",
        "system": (
            "You are a meticulous research analyst. You gather comprehensive information, "
            "verify facts, synthesize findings from multiple sources, identify trends, "
            "and present well-structured reports. You cite sources, acknowledge uncertainty, "
            "and distinguish between facts and opinions."
        ),
        "emoji": "🔍",
        "builtin": True,
    },
    "tutor": {
        "id": "tutor",
        "name": "Personal Tutor",
        "description": "Patient teacher who explains complex concepts simply and interactively",
        "system": (
            "You are a patient and skilled personal tutor. You explain complex concepts "
            "simply, use analogies and examples, check understanding with questions, "
            "adapt to the learner's level, and encourage curiosity. "
            "You make learning engaging and effective."
        ),
        "emoji": "🎓",
        "builtin": True,
    },
    "security": {
        "id": "security",
        "name": "Security Expert",
        "description": "Cybersecurity specialist in vulnerability assessment and secure systems",
        "system": (
            "You are a cybersecurity expert with deep knowledge of penetration testing, "
            "vulnerability assessment, secure coding, OWASP top 10, network security, "
            "and incident response. You help build secure systems and identify risks. "
            "Always operate ethically and legally."
        ),
        "emoji": "🔒",
        "builtin": True,
    },
    "translator": {
        "id": "translator",
        "name": "Translator",
        "description": "Professional translator fluent in many languages",
        "system": (
            "You are a professional translator fluent in Arabic, English, French, Spanish, "
            "German, Chinese, and many other languages. You translate accurately while "
            "preserving meaning, tone, and cultural nuance. You explain translation choices "
            "when needed and handle technical, literary, and business texts."
        ),
        "emoji": "🌐",
        "builtin": True,
    },
}

_PERSONAS_FILE = os.path.join("data", "personas.json")
_lock = threading.Lock()


def _load_custom() -> dict:
    try:
        if os.path.exists(_PERSONAS_FILE):
            with open(_PERSONAS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_custom(customs: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(_PERSONAS_FILE, "w", encoding="utf-8") as f:
        json.dump(customs, f, ensure_ascii=False, indent=2)


def list_personas() -> list[dict]:
    with _lock:
        customs = _load_custom()
    return list({**_BUILTIN_PERSONAS, **customs}.values())


def get_persona(persona_id: str) -> dict | None:
    if persona_id in _BUILTIN_PERSONAS:
        return _BUILTIN_PERSONAS[persona_id]
    with _lock:
        customs = _load_custom()
    return customs.get(persona_id)


def get_system_prompt(persona_id: str) -> str:
    p = get_persona(persona_id)
    return p["system"] if p else _BUILTIN_PERSONAS["default"]["system"]


def create_persona(
    persona_id: str,
    name: str,
    description: str,
    system: str,
    emoji: str = "🤖",
) -> dict:
    persona = {
        "id": persona_id,
        "name": name,
        "description": description,
        "system": system,
        "emoji": emoji,
        "builtin": False,
    }
    with _lock:
        customs = _load_custom()
        customs[persona_id] = persona
        _save_custom(customs)
    return persona


def delete_persona(persona_id: str) -> bool:
    if persona_id in _BUILTIN_PERSONAS:
        return False
    with _lock:
        customs = _load_custom()
        if persona_id not in customs:
            return False
        del customs[persona_id]
        _save_custom(customs)
    return True

```

---

## `core/monitoring.py`

```py
"""Monitoring — track token usage, costs, latency, and request counts."""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

_lock = threading.Lock()

# claude-opus-4-7 pricing per million tokens (as of 2024)
_PRICING = {
    "input": 15.0,
    "output": 75.0,
    "cache_write": 18.75,
    "cache_read": 1.50,
}

_stats = {
    "total_requests": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cache_write_tokens": 0,
    "total_cache_read_tokens": 0,
    "total_cost_usd": 0.0,
    "errors": 0,
    "started_at": datetime.now(timezone.utc).isoformat(),
}

_request_log: deque = deque(maxlen=500)
_latency_by_endpoint: dict = defaultdict(list)


def record_request(
    endpoint: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write: int = 0,
    cache_read: int = 0,
    latency_ms: float = 0.0,
    error: bool = False,
) -> None:
    cost = (
        input_tokens * _PRICING["input"]
        + output_tokens * _PRICING["output"]
        + cache_write * _PRICING["cache_write"]
        + cache_read * _PRICING["cache_read"]
    ) / 1_000_000

    with _lock:
        _stats["total_requests"] += 1
        _stats["total_input_tokens"] += input_tokens
        _stats["total_output_tokens"] += output_tokens
        _stats["total_cache_write_tokens"] += cache_write
        _stats["total_cache_read_tokens"] += cache_read
        _stats["total_cost_usd"] += cost
        if error:
            _stats["errors"] += 1

        _request_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "latency_ms": round(latency_ms),
            "error": error,
        })
        _latency_by_endpoint[endpoint].append(latency_ms)


def get_stats() -> dict:
    with _lock:
        stats = dict(_stats)
        avg_latency = {}
        for ep, latencies in _latency_by_endpoint.items():
            if latencies:
                avg_latency[ep] = round(sum(latencies) / len(latencies))
        stats["avg_latency_ms_by_endpoint"] = avg_latency
        stats["total_cost_usd"] = round(stats["total_cost_usd"], 4)
        return stats


def get_recent_requests(n: int = 50) -> list:
    with _lock:
        return list(_request_log)[-n:]


def get_hourly_summary() -> list:
    with _lock:
        logs = list(_request_log)

    hourly: dict = defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0, "errors": 0})
    for entry in logs:
        hour = entry["ts"][:13]  # "2024-01-01T12"
        hourly[hour]["requests"] += 1
        hourly[hour]["tokens"] += entry["input_tokens"] + entry["output_tokens"]
        hourly[hour]["cost"] += entry["cost_usd"]
        if entry["error"]:
            hourly[hour]["errors"] += 1

    return [{"hour": h, **v} for h, v in sorted(hourly.items())]

```

---

## `core/auth.py`

```py
"""JWT-based authentication middleware."""

import hashlib
import hmac
import logging
import os
import threading
import time
from functools import wraps

from flask import jsonify, request

from core.config import config

logger = logging.getLogger(__name__)

# ── Simple user store (replace with DB in production) ────────────────────────
_users_lock = threading.Lock()
_users: dict[str, str] = {}  # username → hashed_password

# Seed default admin from env
_DEFAULT_USER = os.getenv("ADMIN_USER", "admin")
_DEFAULT_PASS = os.getenv("ADMIN_PASS", "admin123")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _init_default_user() -> None:
    with _users_lock:
        if _DEFAULT_USER not in _users:
            _users[_DEFAULT_USER] = _hash_password(_DEFAULT_PASS)


_init_default_user()


# ── JWT (manual implementation — avoids PyJWT dependency) ────────────────────

import base64
import json as _json


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def _create_token(username: str, expires_in: int = 86400) -> str:
    header = _b64url_encode(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(_json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }).encode())
    msg = f"{header}.{payload}".encode()
    sig = hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"


def _verify_token(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        msg = f"{header}.{payload}".encode()
        expected_sig = hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig), expected_sig):
            return None
        data = _json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


# ── Public helpers ────────────────────────────────────────────────────────────

def login(username: str, password: str) -> str | None:
    with _users_lock:
        stored = _users.get(username)
    if stored and hmac.compare_digest(stored, _hash_password(password)):
        return _create_token(username)
    return None


def register(username: str, password: str) -> bool:
    if len(username) < 3 or len(password) < 6:
        return False
    with _users_lock:
        if username in _users:
            return False
        _users[username] = _hash_password(password)
    return True


def get_current_user() -> dict | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return _verify_token(auth[7:])
    return None


def require_auth(f):
    """Decorator — returns 401 if no valid JWT."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.getenv("AUTH_DISABLED", "false").lower() == "true":
            return f(*args, **kwargs)
        user = get_current_user()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

```

---

## `core/rate_limit.py`

```py
"""Rate Limiting — token-bucket per IP using Flask-Limiter or fallback."""

import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class _TokenBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate        # tokens added per second
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


_buckets: dict[str, _TokenBucket] = defaultdict(
    lambda: _TokenBucket(rate=1.0, capacity=60)   # 60 req/min per IP
)
_buckets_lock = threading.Lock()


def check_rate_limit(ip: str, tokens: int = 1) -> bool:
    with _buckets_lock:
        bucket = _buckets[ip]
    return bucket.consume(tokens)


def get_limiter(app=None):
    """Return a Flask-Limiter instance if available, else None."""
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per minute", "2000 per hour"],
            storage_uri="memory://",
        )
        logger.info("Flask-Limiter initialized")
        return limiter
    except ImportError:
        logger.warning("flask-limiter not installed; using built-in token bucket")
        return None


def rate_limit_middleware(app):
    """Attach rate limiting to Flask app via before_request."""
    from flask import request, jsonify

    @app.before_request
    def _check():
        ip = request.remote_addr or "unknown"
        if not check_rate_limit(ip):
            return jsonify({"error": "Rate limit exceeded. Try again in a moment."}), 429

```

---

## `core/batch.py`

```py
"""Batch Tasks — run multiple tasks concurrently and collect results."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

logger = logging.getLogger(__name__)

_MAX_WORKERS = 5


def run_batch(tasks: list[str], max_workers: int = _MAX_WORKERS) -> dict:
    """Run a list of task strings in parallel. Returns a results dict."""
    batch_id = uuid.uuid4().hex[:10]
    results = {}
    lock = threading.Lock()

    from core.orchestrator import AIOrchestrator

    def _run_one(idx: int, task_text: str) -> tuple[int, dict]:
        orchestrator = AIOrchestrator()
        start = datetime.utcnow()
        try:
            output = orchestrator.run_task_sync(task_text)
            return idx, {
                "task": task_text,
                "status": "completed",
                "output": output,
                "started_at": start.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            return idx, {
                "task": task_text,
                "status": "failed",
                "error": str(exc),
                "started_at": start.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, i, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures):
            idx, result = future.result()
            with lock:
                results[idx] = result

    ordered = [results[i] for i in sorted(results)]
    return {
        "batch_id": batch_id,
        "total": len(tasks),
        "completed": sum(1 for r in ordered if r["status"] == "completed"),
        "failed": sum(1 for r in ordered if r["status"] == "failed"),
        "results": ordered,
    }

```

---

## `core/scheduler.py`

```py
"""Cron-based task scheduler using APScheduler."""

import logging
import threading
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler_instance = None
_lock = threading.Lock()


def get_scheduler() -> "TaskScheduler":
    global _scheduler_instance
    with _lock:
        if _scheduler_instance is None:
            _scheduler_instance = TaskScheduler()
            _scheduler_instance.start()
    return _scheduler_instance


class TaskScheduler:
    def __init__(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            self._aps = BackgroundScheduler(timezone="UTC")
            self._CronTrigger = CronTrigger
            self._available = True
        except ImportError:
            logger.warning("APScheduler not installed. pip install apscheduler")
            self._available = False
            self._aps = None

        self._jobs: dict[str, dict] = {}  # job_id → metadata

    def start(self) -> None:
        if self._available and self._aps:
            self._aps.start()
            logger.info("Scheduler started")

    def _run_task(self, job_id: str, task: str) -> None:
        from core.orchestrator import AIOrchestrator
        logger.info("Scheduler running job %s", job_id)
        if job_id in self._jobs:
            self._jobs[job_id]["last_run"] = datetime.utcnow().isoformat()
            self._jobs[job_id]["run_count"] = self._jobs[job_id].get("run_count", 0) + 1
        try:
            orchestrator = AIOrchestrator()
            output = orchestrator.run_task_sync(task)
            if job_id in self._jobs:
                self._jobs[job_id]["last_output"] = output[:500]
                self._jobs[job_id]["last_status"] = "ok"
        except Exception as exc:
            logger.exception("Scheduled job %s failed", job_id)
            if job_id in self._jobs:
                self._jobs[job_id]["last_status"] = f"error: {exc}"

    def add_job(self, name: str, task: str, cron: str) -> dict:
        job_id = str(uuid.uuid4())[:8]
        meta = {
            "id": job_id,
            "name": name,
            "task": task,
            "cron": cron,
            "created_at": datetime.utcnow().isoformat(),
            "run_count": 0,
            "last_run": None,
            "last_status": None,
            "next_run": None,
        }

        if self._available and self._aps:
            try:
                parts = cron.strip().split()
                if len(parts) != 5:
                    return {"error": "Invalid cron expression. Expected 5 fields: min hour dom mon dow"}
                minute, hour, day, month, day_of_week = parts
                job = self._aps.add_job(
                    self._run_task,
                    trigger=self._CronTrigger(
                        minute=minute, hour=hour, day=day,
                        month=month, day_of_week=day_of_week
                    ),
                    args=[job_id, task],
                    id=job_id,
                )
                next_fire = job.next_run_time
                meta["next_run"] = next_fire.isoformat() if next_fire else None
            except Exception as exc:
                return {"error": f"Failed to schedule: {exc}"}
        else:
            meta["note"] = "APScheduler not installed — job saved but not running"

        self._jobs[job_id] = meta
        return meta

    def remove_job(self, job_id: str) -> bool:
        self._jobs.pop(job_id, None)
        if self._available and self._aps:
            try:
                self._aps.remove_job(job_id)
            except Exception:
                pass
        return True

    def list_jobs(self) -> list[dict]:
        jobs = list(self._jobs.values())
        # Refresh next_run times from APScheduler
        if self._available and self._aps:
            for job in jobs:
                try:
                    aps_job = self._aps.get_job(job["id"])
                    if aps_job and aps_job.next_run_time:
                        job["next_run"] = aps_job.next_run_time.isoformat()
                except Exception:
                    pass
        return jobs

```

---

## `core/rag.py`

```py
"""RAG (Retrieval-Augmented Generation) — upload docs, ask questions."""

import io
import logging
import os
import re
import uuid
from collections import defaultdict

import chromadb

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800       # characters per chunk
CHUNK_OVERLAP = 150
RAG_COLLECTION = "rag_documents"
MAX_CONTEXT_CHUNKS = 6


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end].strip())
        start += size - overlap
    return [c for c in chunks if len(c) > 50]


def _extract_text(file) -> str:
    name = file.filename.lower()
    raw = file.read()

    if name.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        except ImportError:
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(raw))
                return "\n\n".join(p.extract_text() or "" for p in reader.pages)
            except ImportError:
                return raw.decode("utf-8", errors="replace")

    # Plain text / code / markdown / CSV / JSON
    return raw.decode("utf-8", errors="replace")


class RAGEngine:
    def __init__(self, db_path: str):
        os.makedirs(db_path, exist_ok=True)
        self._client = chromadb.PersistentClient(path=db_path)
        self._collection = self._client.get_or_create_collection(
            name=RAG_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def ingest_file(self, file) -> dict:
        name = os.path.basename(file.filename)
        text = _extract_text(file)

        if not text.strip():
            return {"error": "Could not extract text from file", "name": name}

        # Remove existing chunks for this doc
        self.delete_document(name)

        chunks = _chunk_text(text)
        ids = [f"{name}::{i}::{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        metas = [{"doc_name": name, "chunk_index": i} for i in range(len(chunks))]

        # Batch insert (ChromaDB max 5461 per batch)
        batch = 500
        for start in range(0, len(chunks), batch):
            self._collection.add(
                ids=ids[start:start + batch],
                documents=chunks[start:start + batch],
                metadatas=metas[start:start + batch],
            )

        logger.info("Ingested %s → %d chunks", name, len(chunks))
        return {"message": f"✅ تم رفع {name} ({len(chunks)} قطعة)", "name": name, "chunks": len(chunks)}

    def query(self, question: str, n_chunks: int = MAX_CONTEXT_CHUNKS) -> str:
        count = self._collection.count()
        if count == 0:
            return "لا توجد مستندات مرفوعة بعد. ارفع ملفاً أولاً."

        n = min(n_chunks, count)
        results = self._collection.query(query_texts=[question], n_results=n)
        docs = results["documents"][0] if results.get("documents") else []
        metas = results["metadatas"][0] if results.get("metadatas") else []

        if not docs:
            return "لم يتم العثور على معلومات ذات صلة في المستندات."

        context_parts = []
        for doc, meta in zip(docs, metas):
            source = meta.get("doc_name", "?")
            context_parts.append(f"[المصدر: {source}]\n{doc}")
        context = "\n\n---\n\n".join(context_parts)

        prompt = f"""استناداً إلى المقتطفات التالية من المستندات، أجب على السؤال بدقة.
إذا لم تجد الإجابة في المقتطفات، قل ذلك بصراحة.

المقتطفات:
{context}

السؤال: {question}

الإجابة:"""

        result = model_router.chat(
            [{"role": "user", "content": prompt}],
            system="You are a precise document Q&A assistant.",
            max_tokens=2048,
        )
        return result if isinstance(result, str) else "".join(result) or "No answer found"

    def list_documents(self) -> list[dict]:
        if self._collection.count() == 0:
            return []
        result = self._collection.get(limit=10000)
        counts: dict[str, int] = defaultdict(int)
        for meta in (result.get("metadatas") or []):
            if meta:
                counts[meta.get("doc_name", "unknown")] += 1
        return [{"name": name, "chunks": cnt} for name, cnt in counts.items()]

    def delete_document(self, name: str) -> None:
        try:
            existing = self._collection.get(where={"doc_name": name})
            if existing.get("ids"):
                self._collection.delete(ids=existing["ids"])
                logger.info("Deleted document: %s (%d chunks)", name, len(existing["ids"]))
        except Exception as exc:
            logger.warning("Delete doc failed: %s", exc)

```

---

## `core/vision.py`

```py
"""Vision — analyze images using Claude's multimodal capabilities."""

import base64
import io
import logging
import os

import anthropic

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_VISION_SYSTEM = """You are an expert image analyst. Describe and analyze images thoroughly.
Identify objects, text, people, scenes, colors, patterns, and any other relevant details.
If asked a specific question, answer it directly based on what you see in the image.
Respond in the same language as the question."""


class VisionEngine:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._is_claude = model_router.is_claude(config.MODEL)

    def _local_model_unsupported(self) -> str:
        return f"Vision requires a Claude model. Current model '{config.MODEL}' does not support image input. Set MODEL=claude-opus-4-7 (or any claude-*) in .env."

    def _encode_image(self, data: bytes, mime_type: str) -> dict:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.standard_b64encode(data).decode(),
            },
        }

    def analyze(self, image_data: bytes, mime_type: str, question: str = "") -> str:
        if mime_type not in SUPPORTED_TYPES:
            return f"Unsupported image type: {mime_type}. Use JPEG, PNG, GIF, or WebP."
        if not self._is_claude:
            return self._local_model_unsupported()

        prompt = question or "Describe this image in detail. What do you see?"

        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": _VISION_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    self._encode_image(image_data, mime_type),
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    def analyze_from_file(self, file) -> tuple[str, str]:
        """Returns (analysis, mime_type)."""
        data = file.read()
        mime_type = file.content_type or "image/jpeg"
        return self.analyze(data, mime_type), mime_type

    def analyze_from_url(self, url: str, question: str = "") -> str:
        import requests
        r = requests.get(url, timeout=config.WEB_TIMEOUT)
        r.raise_for_status()
        mime_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        return self.analyze(r.content, mime_type, question)

    def compare_images(self, img1: bytes, mime1: str, img2: bytes, mime2: str) -> str:
        if not self._is_claude:
            return self._local_model_unsupported()
        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    self._encode_image(img1, mime1),
                    self._encode_image(img2, mime2),
                    {"type": "text",
                     "text": "Compare these two images in detail. What are the similarities and differences?"},
                ],
            }],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    def extract_text_ocr(self, image_data: bytes, mime_type: str) -> str:
        if not self._is_claude:
            return self._local_model_unsupported()
        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    self._encode_image(image_data, mime_type),
                    {"type": "text",
                     "text": "Extract ALL text from this image exactly as it appears. "
                             "Preserve formatting where possible. Output only the extracted text."},
                ],
            }],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

```

---

## `core/data_analysis.py`

```py
"""Data Analysis — CSV/Excel analysis + chart generation."""

import io
import json
import logging
import os
import uuid

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

CHARTS_DIR = os.path.join("data", "charts")


def _ensure_charts_dir() -> str:
    os.makedirs(CHARTS_DIR, exist_ok=True)
    return CHARTS_DIR


class DataAnalyst:
    def __init__(self):
        pass

    # ── Loaders ───────────────────────────────────────────────────────────────

    def load_csv(self, data: bytes, filename: str = "data.csv") -> "DataAnalyst._Dataset":
        import csv
        text = data.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        columns = reader.fieldnames or []
        return self._Dataset(filename, columns, rows)

    def load_excel(self, data: bytes, filename: str = "data.xlsx") -> "DataAnalyst._Dataset":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            ws = wb.active
            rows_iter = iter(ws.iter_rows(values_only=True))
            headers = [str(h) for h in next(rows_iter, [])]
            rows = [dict(zip(headers, row)) for row in rows_iter]
            return self._Dataset(filename, headers, rows)
        except ImportError:
            raise RuntimeError("openpyxl not installed. pip install openpyxl")

    def load_file(self, file) -> "DataAnalyst._Dataset":
        data = file.read()
        name = file.filename.lower()
        if name.endswith(".csv"):
            return self.load_csv(data, file.filename)
        if name.endswith((".xlsx", ".xls")):
            return self.load_excel(data, file.filename)
        raise ValueError(f"Unsupported format: {name}. Use CSV or Excel.")

    # ── Dataset ───────────────────────────────────────────────────────────────

    class _Dataset:
        def __init__(self, name: str, columns: list, rows: list[dict]):
            self.name = name
            self.columns = list(columns)
            self.rows = rows

        def summary(self) -> str:
            lines = [
                f"**Dataset:** {self.name}",
                f"**Rows:** {len(self.rows)} | **Columns:** {len(self.columns)}",
                f"**Columns:** {', '.join(str(c) for c in self.columns)}",
            ]
            # Numeric stats
            for col in self.columns:
                vals = []
                for r in self.rows:
                    v = r.get(col)
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        pass
                if vals:
                    lines.append(
                        f"  `{col}`: min={min(vals):.2f}, max={max(vals):.2f}, "
                        f"avg={sum(vals)/len(vals):.2f}, count={len(vals)}"
                    )
            # Sample rows
            lines.append("\n**Sample (first 3 rows):**")
            for row in self.rows[:3]:
                lines.append(str({k: row.get(k) for k in self.columns[:6]}))
            return "\n".join(lines)

        def to_csv_text(self, limit: int = 200) -> str:
            import csv, io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=self.columns)
            w.writeheader()
            w.writerows(self.rows[:limit])
            return buf.getvalue()

    # ── AI Analysis ───────────────────────────────────────────────────────────

    def analyze(self, dataset: "_Dataset", question: str = "") -> str:
        prompt_q = question or "Provide a comprehensive analysis of this dataset."
        context = dataset.summary() + "\n\n**CSV sample:**\n" + dataset.to_csv_text(50)

        result = model_router.chat(
            [{"role": "user", "content": f"Dataset info:\n{context}\n\nQuestion: {prompt_q}"}],
            system="You are an expert data analyst. Analyze the provided dataset and answer the question clearly. Use markdown formatting.",
            max_tokens=4096,
        )
        return result if isinstance(result, str) else "".join(result)

    # ── Chart Generation ──────────────────────────────────────────────────────

    def generate_chart(self, dataset: "_Dataset", chart_type: str = "auto",
                       x_col: str = "", y_col: str = "", title: str = "") -> dict:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return {"error": "matplotlib not installed. pip install matplotlib"}

        rows = dataset.rows
        cols = dataset.columns

        # Auto-detect numeric columns
        num_cols = []
        for c in cols:
            try:
                float(rows[0].get(c, "x"))
                num_cols.append(c)
            except (ValueError, TypeError, IndexError):
                pass

        cat_cols = [c for c in cols if c not in num_cols]

        x = x_col or (cat_cols[0] if cat_cols else (cols[0] if cols else ""))
        y = y_col or (num_cols[0] if num_cols else (cols[1] if len(cols) > 1 else ""))

        if not x or not y:
            return {"error": "Could not determine X and Y columns automatically."}

        xs = [str(r.get(x, "")) for r in rows[:50]]
        try:
            ys = [float(r.get(y, 0) or 0) for r in rows[:50]]
        except ValueError:
            return {"error": f"Column '{y}' is not numeric."}

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "bar" or (chart_type == "auto" and len(xs) <= 20):
            ax.bar(xs, ys, color="#6c63ff")
            ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=8)
        elif chart_type == "line" or chart_type == "auto":
            ax.plot(xs, ys, marker="o", color="#6c63ff", linewidth=2)
            ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=8)
        elif chart_type == "pie" and len(xs) <= 10:
            ax.pie(ys, labels=xs, autopct="%1.1f%%")
        elif chart_type == "scatter":
            ax.scatter(xs, ys, color="#6c63ff", alpha=0.7)
        else:
            ax.bar(xs, ys, color="#6c63ff")

        ax.set_title(title or f"{y} by {x}", fontsize=14, fontweight="bold")
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.grid(axis="y", alpha=0.3)
        fig.tight_layout()

        chart_id = uuid.uuid4().hex[:10]
        path = os.path.join(_ensure_charts_dir(), f"chart_{chart_id}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {"chart_id": chart_id, "path": path, "url": f"/api/charts/{chart_id}"}

```

---

## `core/prompt_templates.py`

```py
"""Prompt Templates — save, list, and render reusable prompt templates."""

import json
import logging
import os
import re
import threading
import uuid

logger = logging.getLogger(__name__)

_TEMPLATES_FILE = os.path.join("data", "prompt_templates.json")
_lock = threading.Lock()

_BUILTIN_TEMPLATES = {
    "summarize": {
        "id": "summarize",
        "name": "Summarize Text",
        "description": "Summarize any text concisely",
        "template": "Summarize the following text in {{length}} sentences:\n\n{{text}}",
        "variables": ["text", "length"],
        "builtin": True,
    },
    "translate": {
        "id": "translate",
        "name": "Translate",
        "description": "Translate text to a target language",
        "template": "Translate the following text to {{language}}:\n\n{{text}}",
        "variables": ["text", "language"],
        "builtin": True,
    },
    "code_review": {
        "id": "code_review",
        "name": "Code Review",
        "description": "Review code for bugs, security, and style",
        "template": (
            "Review the following {{language}} code.\n"
            "Check for: bugs, security issues, performance, and style.\n"
            "Provide specific, actionable feedback.\n\n```{{language}}\n{{code}}\n```"
        ),
        "variables": ["code", "language"],
        "builtin": True,
    },
    "explain": {
        "id": "explain",
        "name": "Explain Code",
        "description": "Explain what a piece of code does",
        "template": "Explain what the following {{language}} code does, step by step:\n\n```{{language}}\n{{code}}\n```",
        "variables": ["code", "language"],
        "builtin": True,
    },
    "write_tests": {
        "id": "write_tests",
        "name": "Write Tests",
        "description": "Generate unit tests for code",
        "template": (
            "Write comprehensive unit tests for the following {{language}} code "
            "using {{framework}}:\n\n```{{language}}\n{{code}}\n```"
        ),
        "variables": ["code", "language", "framework"],
        "builtin": True,
    },
    "blog_post": {
        "id": "blog_post",
        "name": "Blog Post",
        "description": "Write a blog post on a topic",
        "template": (
            "Write a {{tone}} blog post about: {{topic}}\n"
            "Target audience: {{audience}}\n"
            "Length: approximately {{words}} words\n"
            "Include: introduction, main points, and conclusion."
        ),
        "variables": ["topic", "tone", "audience", "words"],
        "builtin": True,
    },
}


def _load_custom() -> dict:
    try:
        if os.path.exists(_TEMPLATES_FILE):
            with open(_TEMPLATES_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_custom(customs: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(customs, f, ensure_ascii=False, indent=2)


def list_templates() -> list[dict]:
    with _lock:
        customs = _load_custom()
    return list({**_BUILTIN_TEMPLATES, **customs}.values())


def get_template(template_id: str) -> dict | None:
    if template_id in _BUILTIN_TEMPLATES:
        return _BUILTIN_TEMPLATES[template_id]
    with _lock:
        customs = _load_custom()
    return customs.get(template_id)


def render_template(template_id: str, variables: dict) -> str:
    tmpl = get_template(template_id)
    if not tmpl:
        raise ValueError(f"Template '{template_id}' not found")
    text = tmpl["template"]
    for key, val in variables.items():
        text = text.replace(f"{{{{{key}}}}}", str(val))
    missing = re.findall(r"\{\{(\w+)\}\}", text)
    if missing:
        raise ValueError(f"Missing variables: {', '.join(missing)}")
    return text


def create_template(name: str, template: str, description: str = "",
                    template_id: str | None = None) -> dict:
    tid = template_id or re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]
    variables = re.findall(r"\{\{(\w+)\}\}", template)
    rec = {
        "id": tid,
        "name": name,
        "description": description,
        "template": template,
        "variables": list(dict.fromkeys(variables)),
        "builtin": False,
    }
    with _lock:
        customs = _load_custom()
        customs[tid] = rec
        _save_custom(customs)
    return rec


def delete_template(template_id: str) -> bool:
    if template_id in _BUILTIN_TEMPLATES:
        return False
    with _lock:
        customs = _load_custom()
        if template_id not in customs:
            return False
        del customs[template_id]
        _save_custom(customs)
    return True

```

---

## `core/notifications.py`

```py
"""Webhook and Email notifications — fire when tasks complete."""

import json
import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)

# ── Webhook ───────────────────────────────────────────────────────────────────

_webhooks_lock = threading.Lock()
_webhooks: list[dict] = []  # [{id, url, events, secret}]


def register_webhook(url: str, events: list[str] | None = None, secret: str = "") -> dict:
    import uuid
    wh = {
        "id": uuid.uuid4().hex[:10],
        "url": url,
        "events": events or ["task.completed", "task.failed"],
        "secret": secret,
    }
    with _webhooks_lock:
        _webhooks.append(wh)
    return wh


def remove_webhook(wh_id: str) -> bool:
    with _webhooks_lock:
        before = len(_webhooks)
        _webhooks[:] = [w for w in _webhooks if w["id"] != wh_id]
        return len(_webhooks) < before


def list_webhooks() -> list[dict]:
    with _webhooks_lock:
        return [{"id": w["id"], "url": w["url"], "events": w["events"]} for w in _webhooks]


def _sign_payload(secret: str, payload: bytes) -> str:
    import hashlib
    import hmac
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _fire_webhook(wh: dict, event: str, data: dict) -> None:
    payload = json.dumps({"event": event, "data": data}).encode()
    headers = {"Content-Type": "application/json", "X-AI-Agent-Event": event}
    if wh.get("secret"):
        headers["X-Signature"] = _sign_payload(wh["secret"], payload)
    try:
        r = requests.post(wh["url"], data=payload, headers=headers, timeout=10)
        logger.info("Webhook %s → %s (%d)", event, wh["url"], r.status_code)
    except Exception as exc:
        logger.warning("Webhook delivery failed to %s: %s", wh["url"], exc)


def dispatch_event(event: str, data: dict) -> None:
    """Fire all webhooks that subscribed to this event (async)."""
    with _webhooks_lock:
        targets = [w for w in _webhooks if event in w.get("events", [])]
    for wh in targets:
        t = threading.Thread(target=_fire_webhook, args=(wh, event, data), daemon=True)
        t.start()

    # Also send email if configured
    if os.getenv("NOTIFY_EMAIL"):
        subject = f"AI Agent: {event}"
        body = f"Event: {event}\n\n{json.dumps(data, indent=2, ensure_ascii=False)}"
        _send_email_async(os.getenv("NOTIFY_EMAIL"), subject, body)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        logger.warning("SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        html_body = f"<pre style='font-family:monospace'>{body}</pre>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to, msg.as_string())
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as exc:
        logger.warning("Email failed: %s", exc)
        return False


def _send_email_async(to: str, subject: str, body: str) -> None:
    threading.Thread(target=_send_email, args=(to, subject, body), daemon=True).start()


def send_email(to: str, subject: str, body: str) -> str:
    ok = _send_email(to, subject, body)
    return "✅ Email sent" if ok else "❌ Email failed (check SMTP config)"

```

---

## `core/integrations.py`

```py
"""Slack & Discord integration — send messages, notifications, and results."""

import json
import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")


# ── Slack ─────────────────────────────────────────────────────────────────────

def send_slack_message(text: str, channel: str = "", webhook_url: str = "",
                       blocks: list | None = None) -> dict:
    url = webhook_url or SLACK_WEBHOOK_URL
    token = SLACK_BOT_TOKEN

    if not url and not token:
        return {"error": "SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN not configured"}

    if token and channel:
        try:
            from slack_sdk import WebClient
            client = WebClient(token=token)
            resp = client.chat_postMessage(channel=channel, text=text,
                                            blocks=blocks or [])
            return {"ok": True, "ts": resp["ts"], "channel": resp["channel"]}
        except ImportError:
            pass

    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        r = requests.post(url, json=payload, timeout=10)
        return {"ok": r.ok, "status_code": r.status_code, "text": r.text[:200]}
    except Exception as exc:
        return {"error": str(exc)}


def send_slack_file(channel: str, filename: str, content: str, title: str = "") -> dict:
    token = SLACK_BOT_TOKEN
    if not token:
        return {"error": "SLACK_BOT_TOKEN not configured"}
    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        resp = client.files_upload_v2(
            channel=channel,
            filename=filename,
            content=content,
            title=title or filename,
        )
        return {"ok": True, "file_id": resp["file"]["id"]}
    except ImportError:
        return {"error": "slack-sdk not installed. pip install slack-sdk"}
    except Exception as exc:
        return {"error": str(exc)}


# ── Discord ───────────────────────────────────────────────────────────────────

def send_discord_message(text: str, webhook_url: str = "",
                          username: str = "AI Agent", embeds: list | None = None) -> dict:
    url = webhook_url or DISCORD_WEBHOOK_URL
    if not url:
        return {"error": "DISCORD_WEBHOOK_URL not configured"}

    MAX = 2000
    chunks = [text[i:i+MAX] for i in range(0, len(text), MAX)] if len(text) > MAX else [text]

    results = []
    for chunk in chunks:
        payload: dict = {"username": username, "content": chunk}
        if embeds and chunk == chunks[0]:
            payload["embeds"] = embeds
        try:
            r = requests.post(url, json=payload, timeout=10)
            results.append({"ok": r.ok, "status_code": r.status_code})
        except Exception as exc:
            results.append({"error": str(exc)})

    return {"ok": all(r.get("ok") for r in results), "results": results}


def send_discord_embed(title: str, description: str, color: int = 0x6c63ff,
                        fields: list[dict] | None = None,
                        webhook_url: str = "") -> dict:
    embed = {
        "title": title,
        "description": description[:4096],
        "color": color,
        "fields": fields or [],
    }
    return send_discord_message("", webhook_url=webhook_url, embeds=[embed])


# ── Unified notify ────────────────────────────────────────────────────────────

def notify(message: str, channels: list[str] | None = None) -> dict:
    """Send a notification to all configured channels."""
    channels = channels or ["slack", "discord"]
    results = {}
    threads = []

    def _slack():
        results["slack"] = send_slack_message(message)

    def _discord():
        results["discord"] = send_discord_message(message)

    if "slack" in channels and (SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN):
        t = threading.Thread(target=_slack)
        threads.append(t)
        t.start()

    if "discord" in channels and DISCORD_WEBHOOK_URL:
        t = threading.Thread(target=_discord)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15)

    return results

```

---

## `core/self_healer.py`

```py
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

```

---

## `agents/__init__.py`

```py

```

---

## `agents/planner_agent.py`

```py
import json
import logging

from core import model_router

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM = """You are a task planning expert. Given a complex task, break it into a numbered list of concrete, actionable steps.
Each step must be self-contained and specific enough for an AI agent to execute with tools.
Respond ONLY with a JSON array of step objects: [{"step": 1, "action": "...", "rationale": "..."}]
Keep steps focused and achievable — typically 3-8 steps for most tasks."""


class PlannerAgent:
    def decompose(self, task: str) -> list[dict]:
        """Decompose a task into executable steps."""
        text = model_router.chat(
            [{"role": "user", "content": f"Task to decompose:\n\n{task}"}],
            system=_PLANNER_SYSTEM,
            max_tokens=4096,
        )
        if not isinstance(text, str):
            text = "".join(text)

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            steps = json.loads(text)
            if isinstance(steps, list):
                return steps
        except json.JSONDecodeError:
            logger.warning("Planner returned non-JSON: %s", text[:200])

        # Fallback: treat each line as a step
        lines = [l.strip(" -•*123456789.") for l in text.splitlines() if l.strip()]
        return [{"step": i + 1, "action": line} for i, line in enumerate(lines) if line]

    def format_plan(self, task: str) -> str:
        steps = self.decompose(task)
        lines = [f"**Plan for:** {task}\n"]
        for s in steps:
            n = s.get("step", "?")
            action = s.get("action", str(s))
            rationale = s.get("rationale", "")
            lines.append(f"{n}. {action}")
            if rationale:
                lines.append(f"   _{rationale}_")
        return "\n".join(lines)

```

---

## `agents/executor_agent.py`

```py
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """Executes a sequence of planned steps using registered tool functions."""

    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def register_tool(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn
        logger.debug("Registered tool: %s", name)

    def execute_step(self, step: dict) -> dict:
        tool_name = step.get("tool")
        params = step.get("params", {})
        action = step.get("action", "")

        if tool_name and tool_name in self._tools:
            try:
                result = self._tools[tool_name](**params)
                return {"step": step, "status": "ok", "result": result}
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tool_name, exc)
                return {"step": step, "status": "error", "error": str(exc)}

        # No tool — return the action description for the orchestrator to handle
        return {"step": step, "status": "deferred", "action": action}

    def execute_steps(self, steps: list[dict]) -> list[dict]:
        results = []
        for step in steps:
            result = self.execute_step(step)
            results.append(result)
            if result["status"] == "error":
                logger.warning("Step failed, continuing: %s", result)
        return results

```

---

## `agents/memory_agent.py`

```py
import logging

from core.config import config

logger = logging.getLogger(__name__)


class MemoryAgent:
    """Manages agent memory: store context, search past knowledge, summarize sessions."""

    def __init__(self):
        from memory.memory_manager import MemoryManager
        self.memory = MemoryManager(config.CHROMADB_PATH)

    def remember(self, key: str, content: str, metadata: dict | None = None) -> str:
        self.memory.store(key, content, metadata or {})
        return f"Remembered: {key}"

    def recall(self, query: str, n: int = 5) -> list[dict]:
        return self.memory.search(query, n)

    def recall_formatted(self, query: str, n: int = 5) -> str:
        results = self.recall(query, n)
        if not results:
            return "No relevant memories found."
        lines = [f"**Memories for:** _{query}_\n"]
        for r in results:
            lines.append(f"- **{r.get('key', '?')}**: {r.get('content', '')[:200]}")
        return "\n".join(lines)

    def summarize_and_store(self, session_id: str, conversation: list[dict]) -> str:
        """Summarize a conversation and store it in memory."""
        from core import model_router

        convo_text = "\n".join(
            f"{m['role'].upper()}: {m.get('content', '')}"
            for m in conversation
            if isinstance(m.get("content"), str)
        )

        summary = model_router.chat(
            [{"role": "user", "content": f"Summarize this conversation in 3-5 bullet points:\n\n{convo_text[:8000]}"}],
            max_tokens=1024,
        )
        if not isinstance(summary, str):
            summary = "".join(summary)
        key = f"session:{session_id}"
        self.memory.store(key, summary, {"session_id": session_id, "type": "summary"})
        return summary

```

---

## `agents/coordinator.py`

```py
"""
Multi-Agent Coordinator — orchestrates specialized agents to solve complex tasks.

Modes:
  auto    — routes task to the best single agent
  debate  — agents propose → critique each other → analyst synthesizes final answer
  parallel — all agents work simultaneously, analyst synthesizes
  sequential — agents build on each other's output in a pipeline
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterator

from agents.coder_agent import CoderAgent
from agents.researcher_agent import ResearcherAgent
from agents.analyst_agent import AnalystAgent
from core import model_router

logger = logging.getLogger(__name__)

_ROUTER_SYSTEM = """You are a task routing expert. Given a task, decide which agents should handle it.

Available agents:
- coder: writing code, debugging, code review, programming questions
- researcher: factual questions, research, information gathering, explanations
- analyst: complex reasoning, decision analysis, trade-offs, planning, architecture
- all: tasks that genuinely benefit from multiple perspectives

Respond with ONLY a JSON object:
{"agents": ["coder"], "mode": "auto", "reasoning": "..."}

modes: "auto" (one agent), "debate" (agents discuss), "parallel" (all at once)"""


class MultiAgentCoordinator:
    """Orchestrates coder, researcher, and analyst agents."""

    def __init__(self):
        self.agents = {
            "coder": CoderAgent(),
            "researcher": ResearcherAgent(),
            "analyst": AnalystAgent(),
        }
        self._history: list[dict] = []
        self._lock = threading.Lock()

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route(self, task: str) -> dict:
        """Ask LLM which agents should handle this task."""
        try:
            text = model_router.chat(
                [{"role": "user", "content": task}],
                system=_ROUTER_SYSTEM,
                max_tokens=256,
            )
            if not isinstance(text, str):
                text = "".join(text)
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0:
                return json.loads(text[start:end])
        except Exception as e:
            logger.warning("Routing failed: %s", e)
        return {"agents": ["analyst"], "mode": "auto", "reasoning": "fallback"}

    # ── Execution modes ───────────────────────────────────────────────────────

    def run(self, task: str, mode: str = "auto") -> dict:
        """
        Run the multi-agent system.

        Returns:
            {
                "result": str,          # final answer
                "mode": str,
                "agents_used": list,
                "proposals": dict,      # per-agent proposals (debate/parallel)
                "critiques": dict,      # per-agent critiques (debate)
                "duration_s": float,
            }
        """
        t0 = time.time()

        if mode == "auto":
            routing = self._route(task)
            agent_names = routing.get("agents", ["analyst"])
            if "all" in agent_names:
                mode = "parallel"
                agent_names = list(self.agents.keys())
            elif len(agent_names) == 1:
                agent = self.agents.get(agent_names[0], self.agents["analyst"])
                result = agent.run(task)
                self._record(task, result, agent_names, mode)
                return {
                    "result": result,
                    "mode": "auto",
                    "agents_used": agent_names,
                    "proposals": {},
                    "critiques": {},
                    "routing_reason": routing.get("reasoning", ""),
                    "duration_s": round(time.time() - t0, 2),
                }
            else:
                mode = "parallel"

        if mode == "debate":
            return self._debate(task, t0)
        return self._parallel(task, list(self.agents.keys()), t0)

    def _parallel(self, task: str, agent_names: list[str], t0: float) -> dict:
        """All selected agents work simultaneously; analyst synthesizes."""
        proposals: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=len(agent_names)) as ex:
            futures = {
                ex.submit(self.agents[n].run, task): n
                for n in agent_names
                if n in self.agents and n != "analyst"
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    proposals[name] = future.result()
                except Exception as e:
                    proposals[name] = f"[error: {e}]"

        final = self.agents["analyst"].synthesize(task, proposals, {})
        self._record(task, final, list(proposals.keys()) + ["analyst"], "parallel")
        return {
            "result": final,
            "mode": "parallel",
            "agents_used": list(proposals.keys()) + ["analyst"],
            "proposals": proposals,
            "critiques": {},
            "duration_s": round(time.time() - t0, 2),
        }

    def _debate(self, task: str, t0: float) -> dict:
        """
        Full debate cycle:
        Round 1 — each agent proposes independently
        Round 2 — each agent critiques the others
        Round 3 — analyst synthesizes the best final answer
        """
        agent_names = list(self.agents.keys())

        # Round 1: proposals
        proposals: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=len(agent_names)) as ex:
            futures = {ex.submit(a.propose, task): name for name, a in self.agents.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    proposals[name] = future.result()
                except Exception as e:
                    proposals[name] = f"[error: {e}]"

        # Round 2: critiques (excluding analyst — it synthesizes)
        critiques: dict[str, str] = {}
        critique_agents = {n: a for n, a in self.agents.items() if n != "analyst"}
        with ThreadPoolExecutor(max_workers=len(critique_agents)) as ex:
            futures = {
                ex.submit(a.critique, task, proposals): name
                for name, a in critique_agents.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    critiques[name] = future.result()
                except Exception as e:
                    critiques[name] = f"[error: {e}]"

        # Round 3: synthesis
        final = self.agents["analyst"].synthesize(task, proposals, critiques)
        self._record(task, final, agent_names, "debate")
        return {
            "result": final,
            "mode": "debate",
            "agents_used": agent_names,
            "proposals": proposals,
            "critiques": critiques,
            "duration_s": round(time.time() - t0, 2),
        }

    def stream_run(self, task: str, mode: str = "auto") -> Iterator[str]:
        """Stream progress updates while running multi-agent task."""
        yield f"[Coordinator] Starting multi-agent task (mode={mode})\n"

        routing = {}
        if mode == "auto":
            yield "[Router] Analyzing task to select best agents…\n"
            routing = self._route(task)
            selected = routing.get("agents", ["analyst"])
            reason = routing.get("reasoning", "")
            yield f"[Router] Selected: {', '.join(selected)} — {reason}\n\n"

        yield "[Phase 1] Agents drafting proposals…\n"
        result = self.run(task, mode=mode)

        if result["mode"] in ("debate", "parallel"):
            for name, proposal in result.get("proposals", {}).items():
                agent = self.agents.get(name)
                emoji = getattr(agent, "emoji", "🤖")
                yield f"\n{emoji} [{name.upper()}] Proposal:\n{proposal}\n"

        if result.get("critiques"):
            yield "\n[Phase 2] Agents critiquing each other…\n"
            for name, critique in result["critiques"].items():
                agent = self.agents.get(name)
                emoji = getattr(agent, "emoji", "🤖")
                yield f"\n{emoji} [{name.upper()}] Critique:\n{critique}\n"

        yield f"\n[Phase 3] Analyst synthesizing final answer…\n"
        yield f"\n{'═' * 50}\n"
        yield f"FINAL ANSWER:\n{result['result']}\n"
        yield f"{'═' * 50}\n"
        yield f"\n[Done] Mode={result['mode']} | Agents={', '.join(result['agents_used'])} | Time={result['duration_s']}s\n"

    def get_agents_info(self) -> list[dict]:
        return [
            {
                "name": a.name,
                "description": a.description,
                "emoji": a.emoji,
            }
            for a in self.agents.values()
        ]

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(reversed(self._history[-50:]))

    def _record(self, task: str, result: str, agents: list[str], mode: str):
        with self._lock:
            self._history.append({
                "task": task,
                "result": result[:500],
                "agents": agents,
                "mode": mode,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })


# Singleton
_coordinator: MultiAgentCoordinator | None = None
_coord_lock = threading.Lock()


def get_coordinator() -> MultiAgentCoordinator:
    global _coordinator
    with _coord_lock:
        if _coordinator is None:
            _coordinator = MultiAgentCoordinator()
        return _coordinator

```

---

## `agents/analyst_agent.py`

```py
"""Analyst Agent — specialized in reasoning, problem decomposition, and synthesis."""

import logging

from core import model_router

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert analytical thinker and problem solver.
Your role in the multi-agent team:
- Break down complex problems into clear components
- Apply logical, systematic reasoning
- Identify assumptions, risks, and trade-offs
- Synthesize multiple perspectives into optimal solutions
- Provide structured decision frameworks and recommendations

When analyzing:
- Use structured thinking (pros/cons, decision trees, frameworks)
- Question assumptions explicitly
- Quantify trade-offs where possible
- Provide clear, actionable recommendations

Respond with rigorous analysis and well-reasoned conclusions."""


class AnalystAgent:
    name = "analyst"
    description = "Analytical thinker — reasons, decomposes problems, synthesizes solutions"
    emoji = "📊"

    def _call(self, messages: list[dict], max_tokens: int = 4096) -> str:
        result = model_router.chat(messages, system=_SYSTEM, max_tokens=max_tokens)
        return result if isinstance(result, str) else "".join(result)

    def propose(self, task: str) -> str:
        return self._call([{
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                "Provide your analytical solution. Include: problem decomposition, "
                "key considerations, trade-off analysis, and your recommended approach."
            ),
        }])

    def critique(self, task: str, proposals: dict[str, str]) -> str:
        others = "\n\n".join(
            f"=== {name.upper()} AGENT ===\n{text}"
            for name, text in proposals.items()
            if name != self.name
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Other agents proposed:\n{others}\n\n"
            "From an analytical perspective, critique these proposals. "
            "Identify logical gaps, unstated assumptions, missing trade-offs, "
            "or better solution approaches. Be rigorous."
        )
        return self._call([{"role": "user", "content": prompt}])

    def refine(self, task: str, original: str, critiques: dict[str, str]) -> str:
        critique_text = "\n\n".join(
            f"[{name}]: {text}" for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Your original analysis:\n{original}\n\n"
            f"Critiques received:\n{critique_text}\n\n"
            "Refine your analysis addressing the valid critique points."
        )
        return self._call([{"role": "user", "content": prompt}])

    def synthesize(self, task: str, proposals: dict[str, str], critiques: dict[str, str]) -> str:
        """Final synthesis — combines all proposals and critiques into the optimal answer."""
        proposals_text = "\n\n".join(
            f"=== {name.upper()} PROPOSAL ===\n{text}"
            for name, text in proposals.items()
        )
        critiques_text = "\n\n".join(
            f"=== {name.upper()} CRITIQUE ===\n{text}"
            for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"PROPOSALS FROM TEAM:\n{proposals_text}\n\n"
            f"CRITIQUES FROM TEAM:\n{critiques_text}\n\n"
            "As the synthesizer, produce the final optimal answer that:\n"
            "1. Incorporates the best elements from all proposals\n"
            "2. Addresses the valid critiques\n"
            "3. Resolves any conflicts between perspectives\n"
            "4. Presents a clear, complete, actionable solution\n\n"
            "This is the final answer delivered to the user — make it excellent."
        )
        return self._call([{"role": "user", "content": prompt}], max_tokens=6000)

    def run(self, task: str, context: str = "") -> str:
        msg = task if not context else f"Context:\n{context}\n\nTask: {task}"
        return self._call([{"role": "user", "content": msg}])

```

---

## `agents/coder_agent.py`

```py
"""Coder Agent — specialized in writing, reviewing, and debugging code."""

import logging

from core import model_router

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert software engineer with deep knowledge across all programming languages.
Your role in the multi-agent team:
- Write clean, production-quality code with clear structure
- Debug and fix code issues with root-cause analysis
- Review code for correctness, security, and performance
- Explain code and architecture decisions clearly

When writing code:
- Always include imports
- Handle errors appropriately
- Write efficient, readable code
- Provide brief usage examples when helpful

Respond with concrete code and explanations. Be precise and technical."""


class CoderAgent:
    name = "coder"
    description = "Expert software engineer — writes, reviews, and debugs code"
    emoji = "👨‍💻"

    def _call(self, messages: list[dict], max_tokens: int = 4096) -> str:
        result = model_router.chat(messages, system=_SYSTEM, max_tokens=max_tokens)
        return result if isinstance(result, str) else "".join(result)

    def propose(self, task: str) -> str:
        """Generate a coding solution for the given task."""
        return self._call([{"role": "user", "content": f"Task: {task}\n\nProvide your coding solution:"}])

    def critique(self, task: str, proposals: dict[str, str]) -> str:
        """Review other agents' proposals from a coding quality perspective."""
        others = "\n\n".join(
            f"=== {name.upper()} AGENT ===\n{text}"
            for name, text in proposals.items()
            if name != self.name
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Other agents proposed:\n{others}\n\n"
            "From a software engineering perspective, critique these proposals. "
            "Point out any code issues, missing edge cases, security concerns, or improvements needed. "
            "Be specific and constructive."
        )
        return self._call([{"role": "user", "content": prompt}])

    def refine(self, task: str, original: str, critiques: dict[str, str]) -> str:
        """Refine the original proposal based on critiques."""
        critique_text = "\n\n".join(
            f"[{name}]: {text}" for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Your original proposal:\n{original}\n\n"
            f"Critiques received:\n{critique_text}\n\n"
            "Refine your solution, addressing the valid critiques. "
            "Produce the final, improved version."
        )
        return self._call([{"role": "user", "content": prompt}])

    def run(self, task: str, context: str = "") -> str:
        """Direct task execution — no debate."""
        msg = task if not context else f"Context:\n{context}\n\nTask: {task}"
        return self._call([{"role": "user", "content": msg}])

```

---

## `agents/researcher_agent.py`

```py
"""Researcher Agent — specialized in web search, fact-finding, and synthesis."""

import logging
import requests
from bs4 import BeautifulSoup

from core import model_router

logger = logging.getLogger(__name__)

_SYSTEM = """You are an expert research analyst with strong critical thinking and information synthesis skills.
Your role in the multi-agent team:
- Search for and gather relevant, up-to-date information
- Evaluate source credibility and identify reliable data
- Synthesize information from multiple sources into clear summaries
- Identify knowledge gaps and uncertainties
- Provide well-structured research reports with sources cited

When researching:
- Be objective and evidence-based
- Acknowledge uncertainty when information is unclear
- Prioritize authoritative sources
- Structure findings clearly with key points highlighted

Respond with well-organized research findings."""


class ResearcherAgent:
    name = "researcher"
    description = "Research analyst — searches, gathers, and synthesizes information"
    emoji = "🔍"

    def _call(self, messages: list[dict], max_tokens: int = 4096) -> str:
        result = model_router.chat(messages, system=_SYSTEM, max_tokens=max_tokens)
        return result if isinstance(result, str) else "".join(result)

    def _fetch_url(self, url: str, timeout: int = 10) -> str:
        """Fetch and extract text from a URL."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (research bot)"}
            r = requests.get(url, timeout=timeout, headers=headers)
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)[:6000]
        except Exception as e:
            return f"[fetch error: {e}]"

    def search_and_summarize(self, query: str) -> str:
        """Synthesize knowledge about a query using model knowledge + structured reasoning."""
        prompt = (
            f"Research query: {query}\n\n"
            "Provide a comprehensive research report including:\n"
            "1. Key findings and facts\n"
            "2. Important context and background\n"
            "3. Different perspectives or approaches\n"
            "4. Practical implications\n"
            "5. Key uncertainties or areas needing more information\n\n"
            "Be thorough and cite specific technical details where relevant."
        )
        return self._call([{"role": "user", "content": prompt}])

    def fetch_and_analyze(self, url: str, question: str = "") -> str:
        """Fetch content from a URL and analyze it."""
        content = self._fetch_url(url)
        q = question or "Summarize the key information from this content."
        prompt = f"URL content:\n{content}\n\nQuestion: {q}"
        return self._call([{"role": "user", "content": prompt}])

    def propose(self, task: str) -> str:
        """Generate a research-based solution for the given task."""
        return self._call([{
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                "Provide your research-based analysis and recommendations. "
                "Include relevant facts, context, and evidence-backed conclusions."
            ),
        }])

    def critique(self, task: str, proposals: dict[str, str]) -> str:
        """Review other agents' proposals for factual accuracy and completeness."""
        others = "\n\n".join(
            f"=== {name.upper()} AGENT ===\n{text}"
            for name, text in proposals.items()
            if name != self.name
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Other agents proposed:\n{others}\n\n"
            "From a research and factual accuracy perspective, critique these proposals. "
            "Check for missing context, factual errors, incomplete analysis, or better approaches. "
            "Be specific and evidence-based."
        )
        return self._call([{"role": "user", "content": prompt}])

    def refine(self, task: str, original: str, critiques: dict[str, str]) -> str:
        """Refine the original research based on critiques."""
        critique_text = "\n\n".join(
            f"[{name}]: {text}" for name, text in critiques.items()
        )
        prompt = (
            f"Task: {task}\n\n"
            f"Your original analysis:\n{original}\n\n"
            f"Critiques received:\n{critique_text}\n\n"
            "Refine your research, addressing valid points and filling gaps."
        )
        return self._call([{"role": "user", "content": prompt}])

    def run(self, task: str, context: str = "") -> str:
        """Direct task execution — no debate."""
        msg = task if not context else f"Context:\n{context}\n\nTask: {task}"
        return self.search_and_summarize(msg)

```

---

## `agents/pipeline.py`

```py
"""
Multi-Agent Pipeline: Planner → Researcher → Writer → Reviewer

Each agent is a specialized Claude instance with a focused system prompt.
The pipeline passes results between stages and produces a final polished output.
"""

import logging
from collections.abc import Generator
from dataclasses import dataclass, field

from core import model_router

from core.config import config

logger = logging.getLogger(__name__)

# ── Specialized system prompts ────────────────────────────────────────────────

_PLANNER_SYS = """You are a strategic task planner. Given a goal, output a clear JSON plan:
{"goal": "...", "steps": [{"id": 1, "role": "researcher|writer|analyst|reviewer", "task": "..."}]}
Keep steps focused and sequential. Maximum 5 steps."""

_RESEARCHER_SYS = """You are a thorough researcher. Given a research task, gather all relevant information,
facts, and context needed. Structure your findings clearly with headers and bullet points.
Focus on accuracy and completeness."""

_WRITER_SYS = """You are an expert writer. Given research findings and a writing task,
produce polished, well-structured content. Use clear language, proper formatting, and engaging style.
Adapt tone to the context (technical, creative, business, etc.)."""

_ANALYST_SYS = """You are a data analyst and problem solver. Given data, code, or a technical problem,
provide thorough analysis, identify patterns, suggest solutions, and explain your reasoning clearly."""

_REVIEWER_SYS = """You are a quality reviewer. Review the previous output critically:
1. Check for accuracy, completeness, and clarity
2. Identify any gaps or errors
3. Provide an improved/corrected version
4. Rate quality: Excellent / Good / Needs Work"""

ROLE_SYSTEMS = {
    "planner": _PLANNER_SYS,
    "researcher": _RESEARCHER_SYS,
    "writer": _WRITER_SYS,
    "analyst": _ANALYST_SYS,
    "reviewer": _REVIEWER_SYS,
}


@dataclass
class PipelineResult:
    goal: str
    steps: list[dict] = field(default_factory=list)
    outputs: dict[int, str] = field(default_factory=dict)
    final: str = ""


class MultiAgentPipeline:
    def _call_agent(self, role: str, task: str, context: str = "") -> str:
        system = ROLE_SYSTEMS.get(role, ROLE_SYSTEMS["writer"])
        content = task if not context else f"Context from previous steps:\n{context}\n\nYour task: {task}"
        try:
            result = model_router.chat(
                [{"role": "user", "content": content}],
                system=system,
            )
            return result if isinstance(result, str) else "".join(result)
        except Exception as exc:
            logger.exception("Agent %s failed", role)
            return f"[Error in {role}: {exc}]"

    def _plan(self, goal: str) -> list[dict]:
        import json
        raw = self._call_agent("planner", goal)
        # Strip markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(raw)
            return data.get("steps", [])
        except Exception:
            # Fallback: single researcher + writer + reviewer
            return [
                {"id": 1, "role": "researcher", "task": f"Research everything needed for: {goal}"},
                {"id": 2, "role": "writer", "task": f"Write the final output for: {goal}"},
                {"id": 3, "role": "reviewer", "task": "Review and improve the previous output"},
            ]

    def run(self, goal: str) -> Generator[str, None, None]:
        yield f"🎯 **الهدف:** {goal}\n\n"
        yield "🗺️ **التخطيط…**\n"

        steps = self._plan(goal)
        yield f"خطة من {len(steps)} خطوات\n\n"

        result = PipelineResult(goal=goal, steps=steps)
        accumulated_context = ""

        for step in steps:
            step_id = step.get("id", "?")
            role = step.get("role", "writer")
            task = step.get("task", goal)

            icon = {"researcher": "🔍", "writer": "✍️", "analyst": "📊", "reviewer": "🔎"}.get(role, "🤖")
            yield f"\n{icon} **الخطوة {step_id} — {role}**\n"
            yield f"_{task}_\n\n"

            output = self._call_agent(role, task, accumulated_context)
            result.outputs[step_id] = output
            accumulated_context = f"Step {step_id} ({role}):\n{output}"

            yield output
            yield "\n\n---\n\n"

        result.final = result.outputs.get(max(result.outputs.keys(), default=1), "")
        yield f"✅ **اكتمل pipeline من {len(steps)} مراحل**\n"

    def run_sync(self, goal: str) -> str:
        return "".join(self.run(goal))

```

---

## `agents/digital_twin.py`

```py
"""
Digital Twin Agent — builds a persistent model of the user's thinking style,
coding patterns, and knowledge domains. Answers questions as the user would.

Architecture:
  Ingestion layer  → reads code files, documents, chat history
  Profile builder  → extracts style, patterns, preferences with Claude
  Memory layer     → stores everything in ChromaDB (semantic retrieval)
  Twin responder   → answers questions using the user's mental model
  Probing engine   → asks questions to deepen understanding of the user
"""

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Iterator

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# ── System prompts ──────────────────────────────────────────────────────────

_PROFILER_SYSTEM = """You are an expert at analyzing a person's thinking style, coding patterns,
and intellectual personality from their work.

Analyze the provided content and extract a structured profile containing:
- coding_style: language preferences, naming conventions, architectural choices, complexity tolerance
- problem_approach: how they decompose problems, preferred abstractions, debugging style
- knowledge_domains: their areas of expertise and depth
- learning_style: how they absorb and apply new concepts
- communication_style: how they explain things, level of detail, preferred analogies
- personality_traits: intellectual traits visible in their work (systematic, creative, pragmatic, etc.)

Respond ONLY with a JSON object. No extra text."""

_PROBING_SYSTEM = """You are a thoughtful intellectual companion who is trying to deeply understand
a person's thinking patterns and mental models.

Based on what you know about the user so far, generate ONE insightful probing question that will
reveal something important about how they think, approach problems, or make decisions.

The question should be:
- Specific enough to reveal thinking patterns (not generic)
- Related to their known interests or work
- Open-ended, requiring more than yes/no

Respond with ONLY the question text."""

_TWIN_SYSTEM_TEMPLATE = """You are the Digital Twin of {name}.

You have deeply analyzed {name}'s:
- Coding style and architectural preferences
- Problem-solving approach and thinking patterns
- Knowledge domains and expertise areas
- Communication style and intellectual personality

USER PROFILE:
{profile}

RELEVANT MEMORIES:
{memories}

When answering questions, respond exactly as {name} would:
- Use their characteristic reasoning style
- Draw on their specific knowledge domains
- Apply their preferred solution approaches
- Match their communication style and level of detail
- Reference their past patterns and preferences when relevant

You are NOT a general AI assistant — you are a precise reflection of {name}'s mind."""


class DigitalTwin:
    """Builds and maintains a digital twin of the user."""

    def __init__(self, user_name: str = "the user", chromadb_path: str = ""):
        self._name = user_name
        self._profile: dict = {}
        self._lock = threading.Lock()
        self._ingestion_log: list[dict] = []

        # Vector memory for twin
        chroma_path = chromadb_path or config.CHROMADB_PATH
        self._collection_name = "digital_twin"
        self._init_memory(chroma_path)

    def _init_memory(self, path: str):
        try:
            import chromadb
            self._chroma = chromadb.PersistentClient(path=path)
            self._collection = self._chroma.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            # Load stored profile if it exists
            stored = self._collection.get(ids=["__profile__"])
            if stored["documents"]:
                try:
                    self._profile = json.loads(stored["documents"][0])
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Twin memory init failed: %s", e)
            self._collection = None

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_code(self, code: str, filename: str = "", language: str = "python") -> dict:
        """Analyze a code file and update the user profile."""
        prompt = (
            f"File: {filename or 'unknown'} ({language})\n\n"
            f"```{language}\n{code[:8000]}\n```\n\n"
            "Analyze this code sample and extract the author's profile."
        )
        return self._extract_and_merge_profile(prompt, source=filename or "code")

    def ingest_text(self, text: str, source: str = "") -> dict:
        """Ingest a document (notes, research, messages) and update the profile."""
        prompt = f"Source: {source}\n\nContent:\n{text[:8000]}\n\nAnalyze this content to understand the author's thinking style."
        return self._extract_and_merge_profile(prompt, source=source or "text")

    def ingest_directory(self, path: str, extensions: tuple = (".py", ".md", ".txt")) -> dict:
        """Recursively ingest all matching files from a directory."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}

        results = []
        for f in p.rglob("*"):
            if f.suffix in extensions and f.is_file():
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if len(content) < 50:
                        continue
                    lang = {"py": "python", "md": "markdown", "txt": "text"}.get(f.suffix.lstrip("."), "text")
                    result = self.ingest_code(content, filename=str(f.relative_to(p)), language=lang)
                    results.append({"file": str(f.name), "ok": "error" not in result})
                except Exception as e:
                    results.append({"file": str(f.name), "error": str(e)})

        return {"ingested": len(results), "files": results}

    def _extract_and_merge_profile(self, prompt: str, source: str) -> dict:
        try:
            text = model_router.chat(
                [{"role": "user", "content": prompt}],
                system=_PROFILER_SYSTEM,
                max_tokens=2000,
            )
            if not isinstance(text, str):
                text = "".join(text)
            start, end = text.find("{"), text.rfind("}") + 1
            new_profile = json.loads(text[start:end]) if start >= 0 else {}

            with self._lock:
                self._merge_profile(new_profile)
                self._save_profile()
                self._store_memory(source, prompt[:500], {"type": "ingestion", "source": source})

            log_entry = {"source": source, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "fields": list(new_profile.keys())}
            self._ingestion_log.append(log_entry)
            return {"ok": True, "profile_keys": list(new_profile.keys()), "source": source}
        except Exception as e:
            logger.error("Ingestion failed: %s", e)
            return {"error": str(e), "source": source}

    def _merge_profile(self, new: dict):
        """Deep merge new profile data into existing profile."""
        for key, val in new.items():
            if key not in self._profile:
                self._profile[key] = val
            elif isinstance(val, list) and isinstance(self._profile[key], list):
                # Deduplicate list merge
                existing = set(str(x) for x in self._profile[key])
                self._profile[key].extend(x for x in val if str(x) not in existing)
            elif isinstance(val, dict) and isinstance(self._profile[key], dict):
                self._profile[key].update(val)
            else:
                # Keep latest observation
                self._profile[key] = val

    def _save_profile(self):
        if self._collection is None:
            return
        try:
            doc = json.dumps(self._profile, ensure_ascii=False)
            self._collection.upsert(ids=["__profile__"], documents=[doc],
                                    metadatas=[{"type": "profile"}])
        except Exception as e:
            logger.warning("Profile save failed: %s", e)

    def _store_memory(self, key: str, content: str, metadata: dict):
        if self._collection is None:
            return
        try:
            mid = f"mem_{hash(key + content) % 10**9}"
            self._collection.upsert(ids=[mid], documents=[content], metadatas=[metadata])
        except Exception as e:
            logger.warning("Memory store failed: %s", e)

    def _recall_memories(self, query: str, n: int = 5) -> str:
        if self._collection is None:
            return ""
        try:
            results = self._collection.query(query_texts=[query], n_results=n,
                                              where={"type": "ingestion"})
            docs = results.get("documents", [[]])[0]
            return "\n---\n".join(docs[:n])
        except Exception:
            return ""

    # ── Twin Response ─────────────────────────────────────────────────────────

    def respond(self, question: str, stream: bool = False) -> str | Iterator[str]:
        """Answer a question as the digital twin of the user."""
        memories = self._recall_memories(question)
        profile_text = json.dumps(self._profile, indent=2, ensure_ascii=False) if self._profile else "Profile not yet built."
        system = _TWIN_SYSTEM_TEMPLATE.format(
            name=self._name,
            profile=profile_text[:4000],
            memories=memories[:2000],
        )

        if stream:
            return model_router.chat(
                [{"role": "user", "content": question}],
                system=system,
                max_tokens=3000,
                stream=True,
            )

        result = model_router.chat(
            [{"role": "user", "content": question}],
            system=system,
            max_tokens=3000,
        )
        return result if isinstance(result, str) else "".join(result)

    # ── Probing Engine ────────────────────────────────────────────────────────

    def generate_probing_question(self) -> str:
        """Generate a question designed to reveal the user's thinking patterns."""
        profile_summary = json.dumps(self._profile, ensure_ascii=False)[:3000] if self._profile else "No profile yet."
        result = model_router.chat(
            [{"role": "user", "content": f"What I know about the user so far:\n{profile_summary}"}],
            system=_PROBING_SYSTEM,
            max_tokens=200,
        )
        return (result if isinstance(result, str) else "".join(result)).strip()

    def record_answer(self, question: str, answer: str):
        """Store a probing Q&A pair to deepen the profile."""
        content = f"Q: {question}\nA: {answer}"
        self._store_memory(f"probing_{hash(question)}", content, {"type": "probing"})
        # Also update profile from the answer
        self.ingest_text(answer, source=f"probing_answer")

    # ── Introspection ─────────────────────────────────────────────────────────

    def get_profile(self) -> dict:
        with self._lock:
            return dict(self._profile)

    def get_summary(self) -> str:
        """Return a natural language summary of the user profile."""
        if not self._profile:
            return "Profile not built yet. Ingest some of your code or documents to start."
        result = model_router.chat(
            [{"role": "user", "content": json.dumps(self._profile, ensure_ascii=False)}],
            system="Summarize the provided user profile in 3-4 sentences. Be specific and insightful.",
            max_tokens=500,
        )
        return result if isinstance(result, str) else "".join(result)

    def get_ingestion_log(self) -> list[dict]:
        return list(reversed(self._ingestion_log[-50:]))

    def update_name(self, name: str):
        with self._lock:
            self._name = name


# ── Singleton ──────────────────────────────────────────────────────────────────

_twin: DigitalTwin | None = None
_twin_lock = threading.Lock()


def get_twin(user_name: str = "the user") -> DigitalTwin:
    global _twin
    with _twin_lock:
        if _twin is None:
            _twin = DigitalTwin(user_name=user_name)
        return _twin

```

---

## `tools/__init__.py`

```py

```

---

## `tools/llm_tools.py`

```py
"""LLM Tools — wrappers around model_router for common LLM operations."""

import logging
from collections.abc import Generator

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)


class LLMTools:
    def generate(self, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        result = model_router.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=max_tokens,
        )
        return result if isinstance(result, str) else "".join(result)

    def stream(self, prompt: str, system: str = "", max_tokens: int = 16000) -> Generator[str, None, None]:
        return model_router.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=max_tokens,
            stream=True,
        )

    def classify(self, text: str, categories: list[str]) -> str:
        cats = ", ".join(categories)
        prompt = (
            f"Classify the following text into exactly one of these categories: {cats}\n\n"
            f"Text: {text}\n\nRespond with only the category name."
        )
        return self.generate(prompt, max_tokens=64).strip()

    def summarize(self, text: str, max_words: int = 150) -> str:
        return self.generate(
            f"Summarize the following text in at most {max_words} words:\n\n{text}",
            max_tokens=512,
        )

    def extract_json(self, prompt: str, schema_hint: str = "") -> str:
        full_prompt = prompt
        if schema_hint:
            full_prompt += f"\n\nRespond with valid JSON matching this schema: {schema_hint}"
        else:
            full_prompt += "\n\nRespond with valid JSON only — no markdown, no explanation."
        return self.generate(full_prompt, max_tokens=2048)

    def chat(self, messages: list[dict], system: str = "") -> str:
        result = model_router.chat(messages, system=system, max_tokens=config.MAX_TOKENS)
        return result if isinstance(result, str) else "".join(result)

```

---

## `tools/os_tools.py`

```py
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

```

---

## `tools/web_tools.py`

```py
import logging
import re

from core.config import config

logger = logging.getLogger(__name__)


class WebTools:
    """HTTP-based web tools using requests + BeautifulSoup.
    Falls back to plain text extraction when bs4 is unavailable."""

    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI-Agent/1.0; +https://github.com/AbuSultancom/-ai-agent)"
                )
            })
        return self._session

    def fetch(self, url: str, extract: str = "text") -> str:
        """Fetch a URL and return content based on extract mode."""
        try:
            resp = self.session.get(url, timeout=config.WEB_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if "json" in content_type:
                return resp.text[:8000]

            html = resp.text
            return self._parse_html(html, extract, url)

        except Exception as exc:
            logger.warning("web_fetch failed for %s: %s", url, exc)
            return f"Error fetching {url}: {exc}"

    def _parse_html(self, html: str, extract: str, url: str) -> str:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            if extract == "links":
                links = []
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.get_text(strip=True)
                    if href and not href.startswith("#"):
                        links.append(f"{text}: {href}")
                return "\n".join(links[:100]) or "(no links found)"

            if extract == "html":
                return str(soup)[:10000]

            # text mode
            text = soup.get_text(separator="\n", strip=True)
            # Collapse blank lines
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text[:8000]

        except ImportError:
            # bs4 not installed — strip tags with regex
            if extract == "html":
                return html[:10000]
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:8000]

    def screenshot(self, url: str, output_path: str = "screenshot.png") -> str:
        """Take a screenshot using Playwright (requires playwright to be installed)."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=config.WEB_TIMEOUT * 1000)
                page.screenshot(path=output_path, full_page=True)
                browser.close()
            return f"Screenshot saved to {output_path}"
        except ImportError:
            return "Playwright not installed. Run: pip install playwright && playwright install chromium"
        except Exception as exc:
            return f"Screenshot failed: {exc}"

    def search(self, query: str) -> str:
        """Search DuckDuckGo and return result snippets."""
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        try:
            from bs4 import BeautifulSoup
            resp = self.session.get(url, timeout=config.WEB_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for r in soup.select(".result__body")[:8]:
                title_el = r.select_one(".result__title")
                snippet_el = r.select_one(".result__snippet")
                url_el = r.select_one(".result__url")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                link = url_el.get_text(strip=True) if url_el else ""
                if title:
                    results.append(f"**{title}**\n{link}\n{snippet}")
            return "\n\n".join(results) or "No results found."
        except Exception as exc:
            return f"Search failed: {exc}"

```

---

## `tools/file_tools.py`

```py
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

```

---

## `tools/db_tools.py`

```py
"""Database Tool — execute SQL against SQLite or PostgreSQL."""

import logging
import os
import re
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

_BLOCKED_SQL = re.compile(
    r"(--.*$"                          # inline comment (SQL injection)
    r"|;\s*(DROP|DELETE|UPDATE|INSERT)"  # stacked queries
    r"|UNION\s+SELECT"                 # union injection
    r"|'\s*OR\s+'?\d"                  # classic OR injection
    r"|xp_cmdshell"                    # MSSQL command exec
    r")",
    re.IGNORECASE | re.MULTILINE,
)

_DEFAULT_DB = os.path.join("data", "agent.db")


class DBTools:
    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL", "")
        self._is_pg = self.db_url.startswith("postgresql://") or self.db_url.startswith("postgres://")

    # ── Safety ────────────────────────────────────────────────────────────────

    def _check_safe(self, sql: str) -> None:
        if _BLOCKED_SQL.search(sql):
            raise ValueError("Blocked SQL detected. Use the API carefully.")

    # ── Connection ────────────────────────────────────────────────────────────

    def _sqlite_conn(self, path: str = _DEFAULT_DB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return sqlite3.connect(path)

    def _pg_conn(self):
        try:
            import psycopg2
            return psycopg2.connect(self.db_url)
        except ImportError:
            raise RuntimeError("psycopg2 not installed. pip install psycopg2-binary")

    # ── Execute ───────────────────────────────────────────────────────────────

    def execute(self, sql: str, params: list | None = None,
                db_path: str = _DEFAULT_DB) -> dict[str, Any]:
        self._check_safe(sql)
        params = params or []
        try:
            if self._is_pg:
                conn = self._pg_conn()
            else:
                conn = self._sqlite_conn(db_path)

            with conn:
                cur = conn.cursor()
                cur.execute(sql, params)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, row)) for row in cur.fetchmany(500)]
                    return {"columns": cols, "rows": rows, "rowcount": len(rows)}
                return {"rowcount": cur.rowcount, "rows": []}
        except Exception as exc:
            logger.exception("DB error")
            return {"error": str(exc)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def list_tables(self, db_path: str = _DEFAULT_DB) -> list[str]:
        if self._is_pg:
            result = self.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        else:
            result = self.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                db_path=db_path,
            )
        if "error" in result:
            return []
        return [r.get("name") or r.get("table_name") for r in result["rows"]]

    def describe_table(self, table: str, db_path: str = _DEFAULT_DB) -> dict:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table):
            return {"error": "invalid table name"}
        if self._is_pg:
            result = self.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name = %s ORDER BY ordinal_position",
                [table],
            )
        else:
            result = self.execute(f"PRAGMA table_info({table})", db_path=db_path)
        return result

```

---

## `tools/browser_tools.py`

```py
"""Browser Automation — Playwright-based full browser control."""

import logging
import os
import uuid

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = os.path.join("data", "screenshots")


def _ensure_dir() -> str:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    return SCREENSHOTS_DIR


class BrowserTools:
    def __init__(self):
        self._playwright = None
        self._browser = None

    def _ensure_browser(self):
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=True)
            except ImportError:
                raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")
        return self._browser

    def screenshot(self, url: str, full_page: bool = True) -> dict:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            shot_id = uuid.uuid4().hex[:10]
            path = os.path.join(_ensure_dir(), f"shot_{shot_id}.png")
            page.screenshot(path=path, full_page=full_page)
            return {"shot_id": shot_id, "path": path, "url": f"/api/screenshots/{shot_id}"}
        finally:
            page.close()

    def get_text(self, url: str) -> str:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return page.inner_text("body")
        finally:
            page.close()

    def click_and_get(self, url: str, selector: str) -> str:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.click(selector)
            page.wait_for_load_state("networkidle")
            return page.inner_text("body")
        finally:
            page.close()

    def fill_form(self, url: str, fields: dict[str, str], submit_selector: str = "") -> dict:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            for selector, value in fields.items():
                page.fill(selector, value)
            if submit_selector:
                page.click(submit_selector)
                page.wait_for_load_state("networkidle")
            shot_id = uuid.uuid4().hex[:10]
            path = os.path.join(_ensure_dir(), f"shot_{shot_id}.png")
            page.screenshot(path=path)
            return {
                "success": True,
                "final_url": page.url,
                "screenshot": f"/api/screenshots/{shot_id}",
            }
        finally:
            page.close()

    def extract_links(self, url: str) -> list[dict]:
        browser = self._ensure_browser()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))",
            )
            return links[:100]
        finally:
            page.close()

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None

```

---

## `tools/code_sandbox.py`

```py
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
    "__import__('os').system",
]


def _has_blocked_pattern(code: str) -> str | None:
    for pat in _BLOCKED_IMPORTS:
        if pat in code:
            return pat
    return None


class CodeSandbox:
    def execute(self, code: str, timeout: int = 15) -> dict:
        """Execute Python code in a subprocess. Returns {output, stdout, stderr, success, exit_code, error}."""
        blocked = _has_blocked_pattern(code)
        if blocked:
            return {
                "output": "",
                "stdout": "",
                "stderr": f"Blocked pattern: '{blocked}'",
                "success": False,
                "error": "SecurityError",
                "exit_code": -1,
            }

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
            success = result.returncode == 0
            return {
                "output": stdout,
                "stdout": stdout,
                "stderr": stderr,
                "success": success,
                "error": stderr if not success else None,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"output": "", "stdout": "", "stderr": "", "success": False,
                    "error": f"Timed out after {timeout}s", "exit_code": -1}
        except Exception as exc:
            return {"output": "", "stdout": "", "stderr": "", "success": False,
                    "error": str(exc), "exit_code": -1}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def format_result(self, result: dict) -> str:
        parts = []
        if result.get("error") and not result.get("success"):
            parts.append(f"❌ Error: {result['error']}")
        if result.get("output"):
            parts.append(result["output"])
        if result.get("stderr") and not result.get("output"):
            parts.append(f"stderr:\n{result['stderr']}")
        return "\n".join(parts) or "(no output)"

```

---

## `tools/api_tester.py`

```py
"""API Testing Tool — test any HTTP API with AI-generated assertions."""

import json
import logging
import time
from typing import Any

import requests

from core import model_router

logger = logging.getLogger(__name__)


class APITester:

    def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: Any = None,
        timeout: int = 30,
    ) -> dict:
        method = method.upper()
        headers = headers or {}
        start = time.time()
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                json=body if isinstance(body, (dict, list)) else None,
                data=body if isinstance(body, str) else None,
                timeout=timeout,
            )
            elapsed = round((time.time() - start) * 1000)
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = resp.text[:5000]
            return {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp_body,
                "elapsed_ms": elapsed,
                "ok": resp.ok,
            }
        except Exception as exc:
            return {"error": str(exc), "ok": False}

    def analyze_response(self, request_info: dict, response: dict, expectations: str = "") -> str:
        prompt = (
            f"API Request:\n{json.dumps(request_info, indent=2)}\n\n"
            f"Response:\n{json.dumps(response, indent=2)}\n\n"
        )
        if expectations:
            prompt += f"Expected behavior: {expectations}\n\n"
        prompt += (
            "Analyze this API response. Identify:\n"
            "1. Whether the request succeeded\n"
            "2. Any errors or anomalies\n"
            "3. Response quality and structure\n"
            "4. Suggestions for improvement\n"
            "Be concise and actionable."
        )
        result = model_router.chat([{"role": "user", "content": prompt}], max_tokens=2048)
        return result if isinstance(result, str) else "".join(result)

    def run_test_suite(self, tests: list[dict]) -> list[dict]:
        results = []
        for test in tests:
            method = test.get("method", "GET")
            url = test.get("url", "")
            headers = test.get("headers", {})
            body = test.get("body")
            expectations = test.get("expectations", "")
            name = test.get("name", f"{method} {url}")

            response = self.request(method, url, headers, body)
            analysis = self.analyze_response(
                {"method": method, "url": url, "headers": headers, "body": body},
                response,
                expectations,
            )
            passed = response.get("ok", False)
            results.append({
                "name": name,
                "passed": passed,
                "response": response,
                "analysis": analysis,
            })
        return results

```

---

## `tools/github_tools.py`

```py
"""GitHub API integration tool."""

import logging
import os

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubTools:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self._session = requests.Session()
        if self.token:
            self._session.headers["Authorization"] = f"token {self.token}"
        self._session.headers["Accept"] = "application/vnd.github.v3+json"
        self._session.headers["User-Agent"] = "AI-Agent/1.0"

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        r = self._session.get(f"{GITHUB_API}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = self._session.post(f"{GITHUB_API}{path}", json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        r = self._session.patch(f"{GITHUB_API}{path}", json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    # ── Repos ────────────────────────────────────────────────────────────────

    def get_repo(self, owner: str, repo: str) -> str:
        data = self._get(f"/repos/{owner}/{repo}")
        return (
            f"**{data['full_name']}** ⭐{data['stargazers_count']} 🍴{data['forks_count']}\n"
            f"{data.get('description', '')}\n"
            f"Language: {data.get('language', 'N/A')} | Open issues: {data['open_issues_count']}\n"
            f"URL: {data['html_url']}"
        )

    def list_repos(self, username: str) -> str:
        data = self._get(f"/users/{username}/repos", {"per_page": 20, "sort": "updated"})
        return "\n".join(f"- {r['full_name']} ({r.get('language','?')}) ⭐{r['stargazers_count']}" for r in data)

    # ── Files ────────────────────────────────────────────────────────────────

    def get_file(self, owner: str, repo: str, path: str, ref: str = "HEAD") -> str:
        import base64
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}", {"ref": ref})
        if isinstance(data, list):
            return "\n".join(f"{'📁' if i['type']=='dir' else '📄'} {i['name']}" for i in data)
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return f"```\n{content[:6000]}\n```"

    def list_files(self, owner: str, repo: str, path: str = "", ref: str = "HEAD") -> str:
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}", {"ref": ref})
        if isinstance(data, list):
            return "\n".join(f"{'📁' if i['type']=='dir' else '📄'} {i['path']}" for i in data)
        return data.get("name", "")

    # ── Issues ───────────────────────────────────────────────────────────────

    def list_issues(self, owner: str, repo: str, state: str = "open") -> str:
        data = self._get(f"/repos/{owner}/{repo}/issues", {"state": state, "per_page": 20})
        if not data:
            return f"No {state} issues."
        return "\n".join(f"#{i['number']} {i['title']} [{', '.join(l['name'] for l in i['labels'])}]" for i in data if "pull_request" not in i)

    def create_issue(self, owner: str, repo: str, title: str, body: str = "", labels: list[str] | None = None) -> str:
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        data = self._post(f"/repos/{owner}/{repo}/issues", payload)
        return f"Created issue #{data['number']}: {data['html_url']}"

    def comment_on_issue(self, owner: str, repo: str, number: int, comment: str) -> str:
        data = self._post(f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": comment})
        return f"Commented: {data['html_url']}"

    # ── Pull Requests ─────────────────────────────────────────────────────────

    def list_prs(self, owner: str, repo: str, state: str = "open") -> str:
        data = self._get(f"/repos/{owner}/{repo}/pulls", {"state": state, "per_page": 20})
        if not data:
            return f"No {state} PRs."
        return "\n".join(f"#{p['number']} {p['title']} ({p['head']['ref']} → {p['base']['ref']})" for p in data)

    def create_pr(self, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> str:
        data = self._post(f"/repos/{owner}/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body})
        return f"Created PR #{data['number']}: {data['html_url']}"

    # ── Search ────────────────────────────────────────────────────────────────

    def search_code(self, query: str, repo: str | None = None) -> str:
        q = f"{query} repo:{repo}" if repo else query
        data = self._get("/search/code", {"q": q, "per_page": 10})
        items = data.get("items", [])
        if not items:
            return "No results found."
        return "\n".join(f"- {i['repository']['full_name']}/{i['path']}" for i in items)

    # ── Dispatch (used by orchestrator) ──────────────────────────────────────

    def dispatch(self, action: str, **kwargs) -> str:
        actions = {
            "get_repo": self.get_repo,
            "list_repos": self.list_repos,
            "get_file": self.get_file,
            "list_files": self.list_files,
            "list_issues": self.list_issues,
            "create_issue": self.create_issue,
            "comment_on_issue": self.comment_on_issue,
            "list_prs": self.list_prs,
            "create_pr": self.create_pr,
            "search_code": self.search_code,
        }
        fn = actions.get(action)
        if not fn:
            return f"Unknown GitHub action: {action}"
        try:
            return fn(**kwargs)
        except Exception as exc:
            return f"GitHub error ({action}): {exc}"

```

---

## `tools/docker_tools.py`

```py
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

```

---

## `tools/notify_tools.py`

```py
"""Desktop notification tools — notify-send wrapper + system resource monitor."""

import logging
import shutil
import subprocess
import threading
import time
from typing import Callable

import psutil

logger = logging.getLogger(__name__)

# Alert thresholds (percent)
CPU_THRESHOLD = 85
MEM_THRESHOLD = 85
DISK_THRESHOLD = 90


def send_notification(
    title: str,
    body: str = "",
    urgency: str = "normal",   # low | normal | critical
    icon: str = "dialog-information",
    timeout_ms: int = 5000,
) -> bool:
    """
    Send a desktop notification via notify-send (libnotify).
    Falls back to logger.info if notify-send is not installed.
    """
    if not shutil.which("notify-send"):
        logger.info("NOTIFY [%s]: %s — %s", urgency, title, body)
        return False
    try:
        subprocess.run(
            [
                "notify-send",
                f"--urgency={urgency}",
                f"--icon={icon}",
                f"--expire-time={timeout_ms}",
                title,
                body,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.warning("notify-send error: %s", e)
        return False


def get_system_resources() -> dict:
    """Return current CPU, memory, disk, and top processes."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    top_procs = []
    try:
        procs = sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent") or 0,
            reverse=True,
        )[:5]
        top_procs = [
            {
                "pid": p.info["pid"],
                "name": p.info["name"],
                "cpu": round(p.info.get("cpu_percent") or 0, 1),
                "mem": round(p.info.get("memory_percent") or 0, 1),
            }
            for p in procs
        ]
    except Exception:
        pass

    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / 1e9, 2),
        "memory_total_gb": round(mem.total / 1e9, 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "net_sent_mb": round(net.bytes_sent / 1e6, 1),
        "net_recv_mb": round(net.bytes_recv / 1e6, 1),
        "top_processes": top_procs,
    }


def check_and_alert() -> dict:
    """Check resources and fire desktop notifications if thresholds are exceeded."""
    res = get_system_resources()
    alerts = []

    if res["cpu_percent"] > CPU_THRESHOLD:
        msg = f"CPU at {res['cpu_percent']}%"
        send_notification("⚠️ High CPU Usage", msg, urgency="critical", icon="cpu")
        alerts.append({"type": "cpu", "message": msg})

    if res["memory_percent"] > MEM_THRESHOLD:
        msg = f"RAM at {res['memory_percent']}% ({res['memory_used_gb']:.1f}/{res['memory_total_gb']:.1f} GB)"
        send_notification("⚠️ High Memory Usage", msg, urgency="critical", icon="memory")
        alerts.append({"type": "memory", "message": msg})

    if res["disk_percent"] > DISK_THRESHOLD:
        msg = f"Disk at {res['disk_percent']}% ({res['disk_used_gb']:.0f}/{res['disk_total_gb']:.0f} GB)"
        send_notification("⚠️ Low Disk Space", msg, urgency="critical", icon="drive-harddisk")
        alerts.append({"type": "disk", "message": msg})

    res["alerts"] = alerts
    return res


# ── Background monitor ─────────────────────────────────────────────────────

_monitor_thread: threading.Thread | None = None
_monitor_running = False
_monitor_interval = 60  # seconds
_alert_callbacks: list[Callable] = []


def add_alert_callback(fn: Callable) -> None:
    _alert_callbacks.append(fn)


def _monitor_loop():
    global _monitor_running
    while _monitor_running:
        try:
            result = check_and_alert()
            if result.get("alerts"):
                for cb in _alert_callbacks:
                    try:
                        cb(result)
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Monitor error: %s", e)
        time.sleep(_monitor_interval)


def start_monitor(interval_s: int = 60) -> bool:
    global _monitor_thread, _monitor_running, _monitor_interval
    if _monitor_running:
        return False
    _monitor_interval = interval_s
    _monitor_running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="resource-monitor")
    _monitor_thread.start()
    logger.info("Resource monitor started (interval=%ds)", interval_s)
    return True


def stop_monitor() -> bool:
    global _monitor_running
    if not _monitor_running:
        return False
    _monitor_running = False
    logger.info("Resource monitor stopped")
    return True


def monitor_status() -> dict:
    return {
        "running": _monitor_running,
        "interval_s": _monitor_interval,
        "notify_send_available": bool(shutil.which("notify-send")),
    }

```

---

## `tools/voice_tools.py`

```py
"""Voice tools — Whisper STT transcription, optional TTS output."""

import logging
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Lazy-loaded Whisper model (avoids ~1s import cost at startup)
_whisper_model = None
_whisper_model_size = "base"   # tiny | base | small | medium | large


def _get_model(size: str = _whisper_model_size):
    global _whisper_model, _whisper_model_size
    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "openai-whisper not installed. Run: pip install openai-whisper"
        )
    if _whisper_model is None or size != _whisper_model_size:
        logger.info("Loading Whisper model '%s'…", size)
        _whisper_model = whisper.load_model(size)
        _whisper_model_size = size
    return _whisper_model


def transcribe_file(
    audio_path: str,
    language: str | None = None,
    model_size: str = "base",
) -> dict:
    """
    Transcribe an audio file using Whisper.

    Args:
        audio_path: Path to audio file (wav, mp3, m4a, ogg, webm, …)
        language: ISO code e.g. "en", "ar" — None = auto-detect
        model_size: Whisper model size (tiny/base/small/medium/large)

    Returns:
        {"text": str, "language": str, "duration_s": float, "segments": list}
    """
    model = _get_model(model_size)
    options = {}
    if language:
        options["language"] = language

    result = model.transcribe(audio_path, **options)
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", "unknown"),
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.get("segments", [])
        ],
    }


def transcribe_bytes(
    audio_bytes: bytes,
    ext: str = ".wav",
    language: str | None = None,
    model_size: str = "base",
) -> dict:
    """Transcribe raw audio bytes (saves to temp file, then runs Whisper)."""
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return transcribe_file(tmp_path, language=language, model_size=model_size)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def speak(text: str, rate: int = 175) -> bool:
    """
    Text-to-speech using espeak (if available) or pyttsx3.
    Returns True if speech was produced.
    """
    import shutil
    import subprocess

    if shutil.which("espeak-ng") or shutil.which("espeak"):
        binary = shutil.which("espeak-ng") or "espeak"
        try:
            subprocess.run([binary, f"-s{rate}", text], check=True, capture_output=True)
            return True
        except Exception as e:
            logger.warning("espeak error: %s", e)

    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as e:
        logger.warning("pyttsx3 error: %s", e)

    return False


def whisper_available() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def get_available_models() -> list[str]:
    return ["tiny", "base", "small", "medium", "large"]

```

---

## `memory/__init__.py`

```py

```

---

## `memory/chromadb_client.py`

```py
import logging
import os
import uuid

logger = logging.getLogger(__name__)


class ChromaDBClient:
    """Persistent vector store using ChromaDB."""

    COLLECTION_NAME = "agent_memory"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._client = None
        self._collection = None

    @property
    def client(self):
        if self._client is None:
            import chromadb
            os.makedirs(self.db_path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.db_path)
            logger.info("ChromaDB connected at %s", self.db_path)
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def store_memory(self, key: str, content: str, metadata: dict | None = None) -> None:
        meta = {"key": key, **(metadata or {})}
        # Upsert by key — use key as document id (sanitized)
        doc_id = key.replace(" ", "_")[:512]
        existing = self.collection.get(ids=[doc_id])
        if existing["ids"]:
            self.collection.update(ids=[doc_id], documents=[content], metadatas=[meta])
        else:
            self.collection.add(ids=[doc_id], documents=[content], metadatas=[meta])
        logger.debug("Stored memory: %s", key)

    def retrieve_memory(self, key: str) -> str | None:
        doc_id = key.replace(" ", "_")[:512]
        result = self.collection.get(ids=[doc_id])
        if result["documents"]:
            return result["documents"][0]
        return None

    def search_memory(self, query: str, n_results: int = 5) -> list[dict]:
        count = self.collection.count()
        if count == 0:
            return []
        n = min(n_results, count)
        results = self.collection.query(query_texts=[query], n_results=n)
        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            dist = results["distances"][0][i] if results.get("distances") else None
            output.append(
                {
                    "key": meta.get("key", results["ids"][0][i]),
                    "content": doc,
                    "metadata": meta,
                    "score": round(1 - dist, 4) if dist is not None else None,
                }
            )
        return output

    def delete_memory(self, key: str) -> bool:
        doc_id = key.replace(" ", "_")[:512]
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception as exc:
            logger.warning("Delete failed for key %s: %s", key, exc)
            return False

    def list_memories(self, limit: int = 100) -> list[dict]:
        result = self.collection.get(limit=limit)
        output = []
        for i, doc in enumerate(result["documents"]):
            meta = result["metadatas"][i] if result.get("metadatas") else {}
            output.append({"key": meta.get("key", result["ids"][i]), "content": doc[:200]})
        return output

    def count(self) -> int:
        return self.collection.count()

```

---

## `memory/memory_manager.py`

```py
import logging

from memory.chromadb_client import ChromaDBClient

logger = logging.getLogger(__name__)


class MemoryManager:
    """High-level memory interface used by the orchestrator and agents."""

    def __init__(self, db_path: str):
        self._client = ChromaDBClient(db_path)

    def store(self, key: str, content: str, metadata: dict | None = None) -> None:
        self._client.store_memory(key, content, metadata)

    def retrieve(self, key: str) -> str | None:
        return self._client.retrieve_memory(key)

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        return self._client.search_memory(query, n_results)

    def delete(self, key: str) -> bool:
        return self._client.delete_memory(key)

    def list_all(self, limit: int = 50) -> list[dict]:
        return self._client.list_memories(limit)

    def count(self) -> int:
        return self._client.count()

    def store_conversation_turn(
        self, session_id: str, turn_index: int, role: str, content: str
    ) -> None:
        key = f"conv:{session_id}:{turn_index}:{role}"
        self.store(key, content, {"session_id": session_id, "role": role, "turn": turn_index})

    def get_relevant_context(self, query: str, n: int = 3) -> str:
        results = self.search(query, n)
        if not results:
            return ""
        lines = []
        for r in results:
            lines.append(f"[Memory: {r['key']}]\n{r['content'][:400]}")
        return "\n\n".join(lines)

```

---

## `automation/__init__.py`

```py

```

---

## `automation/briefing.py`

```py
"""Morning briefing generator — fetches news, checks system, summarizes with Claude."""

import logging
import time
from datetime import datetime

import psutil
import requests
from bs4 import BeautifulSoup

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

_NEWS_FEEDS = [
    ("Hacker News", "https://news.ycombinator.com/rss"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
]

_BRIEFING_SYSTEM = """You are a concise morning briefing assistant.
Given news headlines and system status, produce a clear morning briefing that:
- Starts with a short greeting including the date
- Highlights 3-5 most important/interesting tech news items (1-2 sentences each)
- Gives a brief system status summary (1 sentence)
- Ends with a motivational note or key focus for the day

Keep the total briefing under 300 words. Be engaging and direct."""


def _fetch_rss(url: str, max_items: int = 5, timeout: int = 8) -> list[dict]:
    """Fetch RSS feed and return headline dicts."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "briefing-bot/1.0"})
        soup = BeautifulSoup(r.content, "xml")
        items = []
        for item in soup.find_all("item")[:max_items]:
            title = item.find("title")
            desc = item.find("description")
            items.append({
                "title": title.text.strip() if title else "",
                "description": (desc.text[:200].strip() if desc else ""),
            })
        return items
    except Exception as e:
        logger.warning("RSS fetch failed for %s: %s", url, e)
        return []


def _get_system_summary() -> str:
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return (
        f"CPU {cpu}% | RAM {mem.percent}% ({mem.used // 1024**3}/{mem.total // 1024**3} GB) "
        f"| Disk {disk.percent}%"
    )


def generate_briefing(custom_note: str = "") -> dict:
    """
    Generate the morning briefing.

    Returns:
        {"briefing": str, "headlines": list, "system": str, "generated_at": str}
    """
    headlines = []
    for source, url in _NEWS_FEEDS:
        items = _fetch_rss(url, max_items=3)
        for item in items:
            headlines.append({"source": source, **item})

    system_summary = _get_system_summary()
    now = datetime.now().strftime("%A, %B %d %Y — %H:%M")

    headlines_text = "\n".join(
        f"[{h['source']}] {h['title']}: {h['description']}"
        for h in headlines
    ) or "No news fetched."

    prompt = (
        f"Date/Time: {now}\n\n"
        f"News Headlines:\n{headlines_text}\n\n"
        f"System Status: {system_summary}\n"
        + (f"\nSpecial Note: {custom_note}" if custom_note else "")
    )

    result = model_router.chat(
        [{"role": "user", "content": prompt}],
        system=_BRIEFING_SYSTEM,
        max_tokens=600,
    )
    briefing = result if isinstance(result, str) else "".join(result)

    return {
        "briefing": briefing,
        "headlines": headlines,
        "system": system_summary,
        "generated_at": now,
    }

```

---

## `automation/maintenance.py`

```py
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

```

---

## `templates/index.html`

```html
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Agent Dashboard</title>
  <link rel="stylesheet" href="/static/css/main.css" />
</head>
<body>
  <nav class="navbar">
    <div class="nav-brand">🤖 AI Agent</div>
    <div class="nav-tabs">
      <button class="tab-btn active" data-tab="tasks">Tasks</button>
      <button class="tab-btn" data-tab="chat">Chat</button>
      <button class="tab-btn" data-tab="memory">Memory</button>
      <button class="tab-btn" data-tab="rag">Documents</button>
      <button class="tab-btn" data-tab="vision">Vision</button>
      <button class="tab-btn" data-tab="data">Data</button>
      <button class="tab-btn" data-tab="personas">Personas</button>
      <button class="tab-btn" data-tab="templates">Templates</button>
      <button class="tab-btn" data-tab="batch">Batch</button>
      <button class="tab-btn" data-tab="scheduler">Scheduler</button>
      <button class="tab-btn" data-tab="models">Models</button>
      <button class="tab-btn" data-tab="monitoring">Monitoring</button>
      <button class="tab-btn" data-tab="agents">🤝 Agents</button>
      <button class="tab-btn" data-tab="voice">🎙️ Voice</button>
      <button class="tab-btn" data-tab="automation">⚙️ Automation</button>
      <button class="tab-btn" data-tab="healer">🔧 Self-Heal</button>
      <button class="tab-btn" data-tab="twin">🪞 Twin</button>
    </div>
    <div class="nav-right">
      <select id="global-model-select" title="Active model"></select>
      <div id="health-dot" class="health-dot" title="Server status"></div>
    </div>
  </nav>

  <!-- TASKS TAB -->
  <section id="tab-tasks" class="tab-content active">
    <div class="panel">
      <h2>Run a Task</h2>
      <textarea id="task-input" placeholder="Describe your task… e.g. Write a Python script that counts words in a file" rows="4"></textarea>
      <div class="btn-row">
        <button id="run-task-btn" class="btn primary">▶ Run</button>
        <button id="clear-output-btn" class="btn secondary">Clear</button>
      </div>
      <div id="task-output" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>Recent Tasks</h2>
      <button id="refresh-tasks-btn" class="btn secondary small">↻ Refresh</button>
      <div id="tasks-list" class="tasks-list"></div>
    </div>
  </section>

  <!-- CHAT TAB -->
  <section id="tab-chat" class="tab-content">
    <div class="panel chat-panel">
      <div class="chat-top-row">
        <div class="chat-persona-row">
          <label>Persona:</label>
          <select id="persona-select">
            <option value="default">🤖 AI Agent</option>
            <option value="developer">👨‍💻 Senior Developer</option>
            <option value="analyst">📊 Data Analyst</option>
            <option value="writer">✍️ Creative Writer</option>
            <option value="researcher">🔍 Research Analyst</option>
            <option value="tutor">🎓 Personal Tutor</option>
            <option value="security">🔒 Security Expert</option>
            <option value="translator">🌐 Translator</option>
          </select>
        </div>
        <div class="chat-model-row">
          <label>Model:</label>
          <select id="chat-model-select">
            <option value="">Default (config)</option>
          </select>
        </div>
      </div>
      <div id="chat-messages" class="chat-messages"></div>
      <div class="chat-input-row">
        <input id="chat-input" type="text" placeholder="Type your message…" />
        <button id="chat-send-btn" class="btn primary">Send</button>
        <button id="chat-clear-btn" class="btn secondary">Clear</button>
      </div>
    </div>
  </section>

  <!-- MEMORY TAB -->
  <section id="tab-memory" class="tab-content">
    <div class="panel">
      <h2>Search Memory</h2>
      <div class="input-row">
        <input id="memory-query" type="text" placeholder="Search stored memories…" />
        <button id="memory-search-btn" class="btn primary">Search</button>
      </div>
      <div id="memory-results" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>Store a Memory</h2>
      <input id="memory-key" type="text" placeholder="Key (unique identifier)" />
      <textarea id="memory-content" placeholder="Content to store" rows="3"></textarea>
      <button id="memory-store-btn" class="btn primary">Save</button>
      <div id="memory-store-result" class="output-box" style="min-height:40px"></div>
    </div>
  </section>

  <!-- RAG TAB -->
  <section id="tab-rag" class="tab-content">
    <div class="panel">
      <h2>Upload Document</h2>
      <div class="upload-area" id="upload-area">
        <span>Drag a file here or <label for="file-input" class="link">browse</label></span>
        <input id="file-input" type="file" accept=".txt,.pdf,.md,.py,.js,.json,.csv" style="display:none" />
      </div>
      <div id="upload-result" class="output-box" style="min-height:40px"></div>
    </div>
    <div class="panel">
      <h2>Ask a Question</h2>
      <div class="input-row">
        <input id="rag-query" type="text" placeholder="Ask about your documents…" />
        <button id="rag-ask-btn" class="btn primary">Ask</button>
      </div>
      <div id="rag-answer" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>Uploaded Documents</h2>
      <button id="refresh-docs-btn" class="btn secondary small">↻ Refresh</button>
      <div id="docs-list" class="tasks-list"></div>
    </div>
  </section>

  <!-- VISION TAB -->
  <section id="tab-vision" class="tab-content">
    <div class="panel">
      <h2>🖼️ Image Analysis</h2>
      <div class="upload-area" id="vision-upload-area">
        <span>Drag an image here or <label for="vision-file-input" class="link">browse</label></span>
        <input id="vision-file-input" type="file" accept="image/*" style="display:none" />
      </div>
      <img id="vision-preview" class="image-preview" style="display:none" alt="preview" />
      <input id="vision-question" type="text" placeholder="Ask a question about the image (optional)…" />
      <div class="btn-row">
        <button id="vision-analyze-btn" class="btn primary">Analyze</button>
        <button id="vision-ocr-btn" class="btn secondary">Extract Text (OCR)</button>
      </div>
      <div id="vision-result" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>🔗 Analyze from URL</h2>
      <div class="input-row">
        <input id="vision-url" type="text" placeholder="Image URL…" />
        <input id="vision-url-question" type="text" placeholder="Question (optional)" />
        <button id="vision-url-btn" class="btn primary">Analyze</button>
      </div>
      <div id="vision-url-result" class="output-box"></div>
    </div>
  </section>

  <!-- DATA ANALYSIS TAB -->
  <section id="tab-data" class="tab-content">
    <div class="panel">
      <h2>📊 Data Analysis</h2>
      <div class="upload-area" id="data-upload-area">
        <span>Drag a CSV or Excel file here or <label for="data-file-input" class="link">browse</label></span>
        <input id="data-file-input" type="file" accept=".csv,.xlsx,.xls" style="display:none" />
      </div>
      <input id="data-question" type="text" placeholder="Analysis question (optional)…" />
      <div class="btn-row">
        <button id="data-analyze-btn" class="btn primary">Analyze with AI</button>
        <button id="data-summary-btn" class="btn secondary">Summary Only</button>
      </div>
      <div id="data-result" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>📈 Generate Chart</h2>
      <p class="hint">Upload a file above, then choose a chart type below.</p>
      <div class="input-row">
        <select id="chart-type">
          <option value="auto">Auto-detect</option>
          <option value="bar">Bar Chart</option>
          <option value="line">Line Chart</option>
          <option value="pie">Pie Chart</option>
          <option value="scatter">Scatter Plot</option>
        </select>
        <input id="chart-x" type="text" placeholder="X column (optional)" />
        <input id="chart-y" type="text" placeholder="Y column (optional)" />
        <button id="chart-btn" class="btn primary">Generate</button>
      </div>
      <div id="chart-result"></div>
    </div>
  </section>

  <!-- PERSONAS TAB -->
  <section id="tab-personas" class="tab-content">
    <div class="panel">
      <h2>🎭 Available Personas</h2>
      <button id="refresh-personas-btn" class="btn secondary small">↻ Refresh</button>
      <div id="personas-list" class="personas-grid"></div>
    </div>
    <div class="panel">
      <h2>➕ Create Custom Persona</h2>
      <div class="form-grid">
        <input id="persona-id" type="text" placeholder="ID (lowercase, no spaces)" />
        <input id="persona-name" type="text" placeholder="Display name" />
        <input id="persona-emoji" type="text" placeholder="Emoji 🤖" maxlength="4" />
        <input id="persona-desc" type="text" placeholder="Short description" />
        <textarea id="persona-system" placeholder="System prompt — define the AI personality" rows="4"></textarea>
        <button id="persona-create-btn" class="btn primary">Create Persona</button>
      </div>
      <div id="persona-create-result" class="output-box" style="min-height:40px"></div>
    </div>
  </section>

  <!-- PROMPT TEMPLATES TAB -->
  <section id="tab-templates" class="tab-content">
    <div class="panel">
      <h2>📝 Prompt Templates</h2>
      <button id="refresh-templates-btn" class="btn secondary small">↻ Refresh</button>
      <div id="templates-list" class="templates-list"></div>
    </div>
    <div class="panel">
      <h2>▶ Run a Template</h2>
      <select id="template-select"><option value="">— Select a template —</option></select>
      <div id="template-vars-form" class="form-grid"></div>
      <div class="btn-row">
        <button id="template-run-btn" class="btn primary">Run</button>
        <button id="template-preview-btn" class="btn secondary">Preview</button>
      </div>
      <div id="template-result" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>➕ Create New Template</h2>
      <input id="new-tmpl-name" type="text" placeholder="Template name" />
      <input id="new-tmpl-desc" type="text" placeholder="Description" />
      <textarea id="new-tmpl-text" placeholder="Template body — use {{variable}} for placeholders" rows="5"></textarea>
      <button id="new-tmpl-btn" class="btn primary">Save Template</button>
      <div id="new-tmpl-result" class="output-box" style="min-height:40px"></div>
    </div>
  </section>

  <!-- BATCH TASKS TAB -->
  <section id="tab-batch" class="tab-content">
    <div class="panel">
      <h2>⚡ Batch Tasks</h2>
      <p class="hint">Enter one task per line — all will run in parallel.</p>
      <textarea id="batch-input" placeholder="First task&#10;Second task&#10;Third task…" rows="6"></textarea>
      <div class="btn-row">
        <button id="batch-run-btn" class="btn primary">▶ Run All</button>
      </div>
      <div id="batch-result" class="output-box"></div>
    </div>
  </section>

  <!-- SCHEDULER TAB -->
  <section id="tab-scheduler" class="tab-content">
    <div class="panel">
      <h2>Add Scheduled Task</h2>
      <input id="sched-name" type="text" placeholder="Job name" />
      <textarea id="sched-task" placeholder="Task description" rows="3"></textarea>
      <div class="input-row">
        <input id="sched-cron" type="text" placeholder="Cron expression (e.g. 0 8 * * *)" />
        <button id="sched-add-btn" class="btn primary">Add Job</button>
      </div>
      <div id="sched-result" class="output-box" style="min-height:40px"></div>
    </div>
    <div class="panel">
      <h2>Scheduled Jobs</h2>
      <button id="refresh-sched-btn" class="btn secondary small">↻ Refresh</button>
      <div id="sched-list" class="tasks-list"></div>
    </div>
  </section>

  <!-- MODELS TAB -->
  <section id="tab-models" class="tab-content">
    <div class="panel">
      <h2>🧠 Available Models</h2>
      <button id="refresh-models-btn" class="btn secondary small">↻ Refresh</button>
      <div id="models-status" class="hint"></div>
      <div id="models-grid" class="models-grid"></div>
    </div>
    <div class="panel">
      <h2>⬇️ Pull a Local Model</h2>
      <p class="hint">Requires <a href="https://ollama.com" target="_blank" class="link">Ollama</a> running locally.</p>
      <div class="input-row">
        <select id="pull-model-select">
          <option value="llama3.2">llama3.2 (3B — fast)</option>
          <option value="llama3.1">llama3.1 (8B)</option>
          <option value="mistral">mistral (7B)</option>
          <option value="mixtral">mixtral (47B MoE)</option>
          <option value="qwen2.5">qwen2.5 (7B)</option>
          <option value="qwen2.5-coder">qwen2.5-coder (7B — code)</option>
          <option value="deepseek-r1">deepseek-r1 (7B — reasoning)</option>
          <option value="phi4">phi4 (14B — Microsoft)</option>
          <option value="gemma2">gemma2 (9B — Google)</option>
          <option value="codellama">codellama (7B — code)</option>
        </select>
        <input id="pull-model-custom" type="text" placeholder="or type model name…" />
        <button id="pull-model-btn" class="btn primary">Pull</button>
      </div>
      <div id="pull-result" class="output-box" style="min-height:40px"></div>
    </div>
  </section>

  <!-- MONITORING TAB -->
  <section id="tab-monitoring" class="tab-content">
    <div class="panel">
      <h2>📊 Usage Statistics</h2>
      <button id="refresh-stats-btn" class="btn secondary small">↻ Refresh</button>
      <div id="stats-grid" class="stats-grid"></div>
    </div>
    <div class="panel">
      <h2>📜 Recent Requests</h2>
      <div id="requests-list" class="output-box" style="max-height:400px;overflow-y:auto"></div>
    </div>
    <div class="panel">
      <h2>📈 Hourly Summary</h2>
      <div id="hourly-list" class="output-box" style="max-height:300px;overflow-y:auto"></div>
    </div>
  </section>

  <!-- MULTI-AGENT SYSTEM TAB -->
  <section id="tab-agents" class="tab-content">
    <div class="panel">
      <h2>🤝 Agent Team</h2>
      <div id="agents-grid" class="personas-grid"></div>
    </div>
    <div class="panel">
      <h2>🧠 Run Multi-Agent Task</h2>
      <p class="hint">Agents collaborate, debate, and synthesize the optimal answer together.</p>
      <textarea id="agent-task-input" placeholder="Describe a complex task for the agent team… e.g. Design a secure REST API for user authentication" rows="4"></textarea>
      <div class="btn-row">
        <select id="agent-mode-select" style="width:auto;margin-bottom:0">
          <option value="auto">Auto (smart routing)</option>
          <option value="debate">Debate (full discussion)</option>
          <option value="parallel">Parallel (all at once)</option>
        </select>
        <button id="agent-run-btn" class="btn primary">▶ Run Team</button>
      </div>
      <div id="agent-output" class="output-box" style="min-height:160px"></div>
    </div>
    <div class="panel">
      <h2>📜 Team History</h2>
      <button id="refresh-agent-history-btn" class="btn secondary small">↻ Refresh</button>
      <div id="agent-history" class="tasks-list"></div>
    </div>
  </section>

  <!-- VOICE TAB -->
  <section id="tab-voice" class="tab-content">
    <div class="panel">
      <h2>🎙️ Voice Input (Whisper)</h2>
      <div id="voice-status" class="hint"></div>
      <div class="upload-area" id="voice-upload-area">
        <span>Drop an audio file here or <label for="voice-file-input" class="link">browse</label></span>
        <input id="voice-file-input" type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm" style="display:none" />
      </div>
      <div class="input-row" style="margin-top:10px">
        <select id="voice-model-select" style="width:auto;margin-bottom:0;flex:0 0 auto">
          <option value="tiny">tiny (fastest)</option>
          <option value="base" selected>base (balanced)</option>
          <option value="small">small (better)</option>
          <option value="medium">medium (accurate)</option>
        </select>
        <input id="voice-language" type="text" placeholder="Language code (auto-detect if empty)" style="margin-bottom:0;flex:1" />
      </div>
      <div class="btn-row">
        <button id="voice-transcribe-btn" class="btn primary">Transcribe</button>
        <button id="voice-run-btn" class="btn secondary">Transcribe &amp; Run as Task</button>
      </div>
      <div id="voice-result" class="output-box"></div>
    </div>
    <div class="panel">
      <h2>🎤 Record (Browser)</h2>
      <p class="hint">Record directly from your microphone and transcribe.</p>
      <div class="btn-row">
        <button id="voice-record-btn" class="btn primary">⏺ Start Recording</button>
        <button id="voice-stop-btn" class="btn secondary" disabled>⏹ Stop</button>
      </div>
      <audio id="voice-playback" controls style="width:100%;margin-bottom:12px;display:none"></audio>
      <div id="voice-record-result" class="output-box" style="min-height:60px"></div>
    </div>
  </section>

  <!-- AUTOMATION TAB -->
  <section id="tab-automation" class="tab-content">
    <div class="panel">
      <h2>🌅 Morning Briefing</h2>
      <p class="hint">Fetches tech news and generates a personalized daily briefing with AI.</p>
      <input id="briefing-note" type="text" placeholder="Custom note for today (optional)…" />
      <button id="briefing-btn" class="btn primary">Generate Briefing</button>
      <div id="briefing-result" class="output-box" style="min-height:120px"></div>
    </div>
    <div class="panel">
      <h2>💻 System Resources</h2>
      <button id="refresh-resources-btn" class="btn secondary small">↻ Refresh</button>
      <button id="monitor-start-btn" class="btn secondary small">▶ Start Monitor</button>
      <button id="monitor-stop-btn" class="btn secondary small">⏹ Stop Monitor</button>
      <div id="monitor-status" class="hint" style="margin-top:8px"></div>
      <div id="resources-grid" class="stats-grid" style="margin-top:12px"></div>
      <div id="top-processes" class="output-box" style="min-height:80px;margin-top:12px"></div>
    </div>
    <div class="panel">
      <h2>🧹 System Maintenance</h2>
      <p class="hint">Clean temporary files and old logs. Use Dry Run first to preview changes.</p>
      <div class="btn-row">
        <select id="maintenance-action" style="width:auto;margin-bottom:0">
          <option value="all">All maintenance</option>
          <option value="temp">Temp files only</option>
          <option value="logs">Old logs only</option>
          <option value="disk">Disk report only</option>
        </select>
        <button id="maintenance-dry-btn" class="btn secondary">Dry Run (Preview)</button>
        <button id="maintenance-run-btn" class="btn danger">Run Cleanup</button>
      </div>
      <div id="maintenance-result" class="output-box" style="min-height:80px"></div>
    </div>
    <div class="panel">
      <h2>🔔 Desktop Notification</h2>
      <input id="notif-title" type="text" placeholder="Title" />
      <input id="notif-body" type="text" placeholder="Message body…" />
      <div class="input-row">
        <select id="notif-urgency" style="width:auto;margin-bottom:0">
          <option value="low">Low</option>
          <option value="normal" selected>Normal</option>
          <option value="critical">Critical</option>
        </select>
        <button id="notif-send-btn" class="btn primary">Send Notification</button>
      </div>
      <div id="notif-result" class="output-box" style="min-height:40px"></div>
    </div>
  </section>

  <!-- SELF-HEALING TAB -->
  <section id="tab-healer" class="tab-content">
    <div class="panel">
      <h2>🔧 Analyze &amp; Fix an Error</h2>
      <p class="hint">Paste an error traceback — the system will generate and optionally apply a code patch.</p>
      <textarea id="heal-error" placeholder="Paste error traceback here…" rows="6"></textarea>
      <input id="heal-task" type="text" placeholder="What task triggered this error? (optional context)" />
      <input id="heal-file" type="text" placeholder="File hint e.g. core/orchestrator.py (optional)" />
      <div class="btn-row">
        <button id="heal-analyze-btn" class="btn primary">🔍 Analyze</button>
        <button id="heal-auto-btn" class="btn secondary">⚡ Analyze + Auto-Apply</button>
      </div>
      <div id="heal-result" class="output-box" style="min-height:120px"></div>
    </div>
    <div class="panel">
      <h2>📜 Heal Log</h2>
      <button id="refresh-heal-log-btn" class="btn secondary small">↻ Refresh</button>
      <button id="refresh-backups-btn" class="btn secondary small">📦 Backups</button>
      <div id="heal-log" class="tasks-list" style="margin-top:12px"></div>
    </div>
  </section>

  <!-- DIGITAL TWIN TAB -->
  <section id="tab-twin" class="tab-content">
    <div class="panel">
      <h2>🪞 Your Digital Twin</h2>
      <div class="input-row">
        <input id="twin-name" type="text" placeholder="Your name (personalizes the twin)" style="margin-bottom:0" />
        <button id="twin-name-btn" class="btn secondary">Set Name</button>
      </div>
      <button id="twin-profile-btn" class="btn primary" style="margin-top:10px">Load Profile &amp; Summary</button>
      <div id="twin-summary" class="output-box" style="min-height:80px;margin-top:10px"></div>
    </div>
    <div class="panel">
      <h2>📥 Train Your Twin</h2>
      <p class="hint">Upload code files, notes, or documents — the twin learns your thinking style.</p>
      <div class="upload-area" id="twin-upload-area">
        <span>Drop files here or <label for="twin-file-input" class="link">browse</label></span>
        <input id="twin-file-input" type="file" accept=".py,.md,.txt,.js,.ts,.java,.cpp,.rs" multiple style="display:none" />
      </div>
      <input id="twin-dir" type="text" placeholder="Or ingest a full directory path e.g. ~/projects/myapp" />
      <div class="btn-row">
        <button id="twin-ingest-file-btn" class="btn primary">Ingest Files</button>
        <button id="twin-ingest-dir-btn" class="btn secondary">Ingest Directory</button>
      </div>
      <div id="twin-ingest-result" class="output-box" style="min-height:40px"></div>
    </div>
    <div class="panel">
      <h2>💬 Ask Your Twin</h2>
      <p class="hint">The twin answers based on YOUR thinking style, not generic AI.</p>
      <textarea id="twin-question" placeholder="Ask your twin anything… e.g. How would I design a caching layer for this project?" rows="3"></textarea>
      <button id="twin-ask-btn" class="btn primary">Ask Twin</button>
      <div id="twin-answer" class="output-box" style="min-height:100px"></div>
    </div>
    <div class="panel">
      <h2>🧠 Probing Session</h2>
      <p class="hint">The twin asks you questions to better understand your thinking patterns.</p>
      <button id="twin-probe-btn" class="btn secondary">Generate Question</button>
      <div id="twin-probe-question" class="output-box" style="min-height:50px;margin:10px 0"></div>
      <textarea id="twin-probe-answer" placeholder="Your answer…" rows="3"></textarea>
      <button id="twin-probe-submit-btn" class="btn primary">Submit Answer</button>
      <div id="twin-probe-result" class="output-box" style="min-height:40px"></div>
    </div>
  </section>

  <div id="toast" class="toast"></div>
  <script src="/static/js/main.js"></script>
</body>
</html>

```

---

## `static/js/main.js`

```js
/* ───────── Helpers ───────── */
const $ = id => document.getElementById(id);
const API = path => fetch(path, { headers: getAuthHeader() });
const APIJ = (path, body, method = 'POST') =>
  fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(body),
  });

function getAuthHeader() {
  const token = localStorage.getItem('jwt_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function getActiveModel() {
  return localStorage.getItem('active_model') || '';
}

function setActiveModel(model) {
  localStorage.setItem('active_model', model);
  const gSel = $('global-model-select');
  if (gSel && model) gSel.value = model;
  const cSel = $('chat-model-select');
  if (cSel && model) cSel.value = model;
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60) return `${Math.round(diff)}s`;
  if (diff < 3600) return `${Math.round(diff / 60)}m`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h`;
  return `${Math.round(diff / 86400)}d`;
}

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showToast(msg, type = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.style.borderColor = type === 'ok' ? 'var(--ok)' : 'var(--err)';
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

/* ───────── Health check ───────── */
async function checkHealth() {
  try {
    const r = await API('/health');
    $('health-dot').className = r.ok ? 'health-dot ok' : 'health-dot err';
  } catch { $('health-dot').className = 'health-dot err'; }
}
checkHealth();
setInterval(checkHealth, 30000);

/* ───────── Tab navigation ───────── */
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
    if (btn.dataset.tab === 'models') loadModels();
    if (btn.dataset.tab === 'monitoring') loadMonitoring();
  });
});

/* ═══════════════════════════════════════
   TAB 1 — TASKS
═══════════════════════════════════════ */
const taskOutput = $('task-output');
let currentEventSource = null;

async function runTask() {
  const task = $('task-input').value.trim();
  if (!task) return;
  const btn = $('run-task-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Running… <span class="spinner"></span>';
  taskOutput.textContent = '';

  try {
    const model = getActiveModel();
    const body = { task };
    if (model) body.model = model;
    const res = await APIJ('/api/task', body);
    const { task_id } = await res.json();
    if (!task_id) throw new Error('Task creation failed');

    if (currentEventSource) currentEventSource.close();
    currentEventSource = new EventSource(`/api/task/${task_id}/stream`);
    currentEventSource.onmessage = e => {
      taskOutput.textContent += e.data;
      taskOutput.scrollTop = taskOutput.scrollHeight;
    };
    currentEventSource.addEventListener('done', e => {
      currentEventSource.close();
      btn.disabled = false;
      btn.textContent = '▶ Run';
      loadTasks();
      showToast(e.data === 'completed' ? '✅ Task completed' : '❌ Task failed',
        e.data === 'completed' ? 'ok' : 'err');
    });
    currentEventSource.onerror = () => {
      currentEventSource.close();
      btn.disabled = false;
      btn.textContent = '▶ Run';
    };
  } catch (err) {
    taskOutput.textContent = `Error: ${err.message}`;
    btn.disabled = false;
    btn.textContent = '▶ Run';
  }
}

$('run-task-btn').addEventListener('click', runTask);
$('task-input').addEventListener('keydown', e => { if (e.ctrlKey && e.key === 'Enter') runTask(); });
$('clear-output-btn').addEventListener('click', () => { taskOutput.textContent = ''; });
$('refresh-tasks-btn').addEventListener('click', loadTasks);

async function loadTasks() {
  try {
    const r = await API('/api/tasks');
    const { tasks } = await r.json();
    const list = $('tasks-list');
    if (!tasks.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No tasks yet</p>'; return; }
    list.innerHTML = tasks.map(t => `
      <div class="task-card" onclick="showTaskOutput('${t.id}','${escHtml(t.task)}')">
        <div class="task-head">
          <span class="task-text">${escHtml(t.task)}</span>
          <span class="task-time">${timeAgo(t.created_at)}</span>
          <span class="badge ${t.status}">${t.status}</span>
        </div>
      </div>`).join('');
  } catch { }
}

function showTaskOutput(id, taskText) {
  $('task-input').value = taskText;
  API(`/api/task/${id}`).then(r => r.json()).then(t => {
    taskOutput.textContent = t.output || '(no output)';
    taskOutput.scrollTop = taskOutput.scrollHeight;
  });
}

loadTasks();

/* ═══════════════════════════════════════
   TAB 2 — CHAT (with Personas)
═══════════════════════════════════════ */
let chatHistory = JSON.parse(localStorage.getItem('chat_history') || '[]');

function renderChat() {
  const msgs = $('chat-messages');
  msgs.innerHTML = chatHistory.map(m => `
    <div class="msg ${m.role}">${renderMarkdown(escHtml(m.content))}</div>`).join('');
  msgs.scrollTop = msgs.scrollHeight;
}

async function sendChat() {
  const input = $('chat-input');
  const text = input.value.trim();
  if (!text) return;
  const personaId = $('persona-select').value;
  const modelOverride = $('chat-model-select').value || getActiveModel() || '';
  input.value = '';
  chatHistory.push({ role: 'user', content: text });
  renderChat();

  const typing = document.createElement('div');
  typing.className = 'msg assistant typing';
  typing.textContent = 'Typing…';
  $('chat-messages').appendChild(typing);
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;

  try {
    const endpoint = personaId !== 'default' ? '/api/chat/persona' : '/api/chat';
    const body = personaId !== 'default'
      ? { message: text, persona_id: personaId }
      : { message: text, history: chatHistory.slice(-20) };
    if (modelOverride) body.model = modelOverride;
    const res = await APIJ(endpoint, body);
    const data = await res.json();
    typing.remove();
    const reply = data.reply || data.error || 'No response';
    chatHistory.push({ role: 'assistant', content: reply });
    localStorage.setItem('chat_history', JSON.stringify(chatHistory.slice(-60)));
    renderChat();
  } catch (err) {
    typing.remove();
    chatHistory.push({ role: 'assistant', content: `Error: ${err.message}` });
    renderChat();
  }
}

$('chat-send-btn').addEventListener('click', sendChat);
$('chat-input').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(); });
$('chat-clear-btn').addEventListener('click', () => {
  chatHistory = [];
  localStorage.removeItem('chat_history');
  renderChat();
  APIJ('/api/chat/clear', {});
});

renderChat();

/* ═══════════════════════════════════════
   TAB 3 — MEMORY
═══════════════════════════════════════ */
$('memory-search-btn').addEventListener('click', async () => {
  const q = $('memory-query').value.trim();
  if (!q) return;
  const box = $('memory-results');
  box.textContent = 'Searching…';
  try {
    const r = await APIJ('/api/memory/search', { query: q, n_results: 8 });
    const { results } = await r.json();
    if (!results.length) { box.textContent = 'No results found'; return; }
    box.innerHTML = results.map(r =>
      `<div style="margin-bottom:12px"><strong style="color:var(--accent2)">${escHtml(r.key)}</strong>` +
      `<span style="color:var(--muted);font-size:12px"> (${r.score || ''})</span><br>${escHtml(r.content)}</div>`
    ).join('<hr style="border-color:var(--border);margin:10px 0">');
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('memory-store-btn').addEventListener('click', async () => {
  const key = $('memory-key').value.trim();
  const content = $('memory-content').value.trim();
  if (!key || !content) return showToast('Key and content are required', 'err');
  const r = await APIJ('/api/memory', { key, content });
  const data = await r.json();
  $('memory-store-result').textContent = data.stored ? `✅ Saved: ${key}` : JSON.stringify(data);
  $('memory-key').value = '';
  $('memory-content').value = '';
});

/* ═══════════════════════════════════════
   TAB 4 — RAG
═══════════════════════════════════════ */
const uploadArea = $('upload-area');
const fileInput = $('file-input');

uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', e => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  uploadFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => uploadFiles(fileInput.files));

async function uploadFiles(files) {
  const result = $('upload-result');
  for (const file of files) {
    result.textContent = `Uploading ${file.name}…`;
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/rag/upload', { method: 'POST', body: fd, headers: getAuthHeader() });
      const data = await r.json();
      result.textContent = data.message || JSON.stringify(data);
      showToast(`✅ ${file.name} uploaded`, 'ok');
      loadDocs();
    } catch (e) { result.textContent = `Error: ${e.message}`; }
  }
}

$('rag-ask-btn').addEventListener('click', async () => {
  const q = $('rag-query').value.trim();
  if (!q) return;
  const box = $('rag-answer');
  box.textContent = 'Searching documents…';
  try {
    const r = await APIJ('/api/rag/query', { query: q });
    const data = await r.json();
    box.textContent = data.answer || data.error || 'No answer found';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('refresh-docs-btn').addEventListener('click', loadDocs);

async function loadDocs() {
  try {
    const r = await API('/api/rag/documents');
    const { documents } = await r.json();
    const list = $('docs-list');
    if (!documents.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No documents yet</p>'; return; }
    list.innerHTML = documents.map(d => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">📄 ${escHtml(d.name)}</span>
          <span class="task-time">${d.chunks} chunks</span>
          <button class="btn danger small" onclick="deleteDoc('${escHtml(d.name)}')">Delete</button>
        </div>
      </div>`).join('');
  } catch { }
}

async function deleteDoc(name) {
  await APIJ('/api/rag/documents', { name }, 'DELETE');
  loadDocs();
  showToast(`🗑️ ${name} deleted`);
}

loadDocs();

/* ═══════════════════════════════════════
   TAB 5 — VISION
═══════════════════════════════════════ */
let visionFile = null;
const visionArea = $('vision-upload-area');
const visionInput = $('vision-file-input');
const visionPreview = $('vision-preview');

visionArea.addEventListener('click', () => visionInput.click());
visionArea.addEventListener('dragover', e => { e.preventDefault(); visionArea.classList.add('dragover'); });
visionArea.addEventListener('dragleave', () => visionArea.classList.remove('dragover'));
visionArea.addEventListener('drop', e => {
  e.preventDefault();
  visionArea.classList.remove('dragover');
  if (e.dataTransfer.files[0]) setVisionFile(e.dataTransfer.files[0]);
});
visionInput.addEventListener('change', () => { if (visionInput.files[0]) setVisionFile(visionInput.files[0]); });

function setVisionFile(file) {
  visionFile = file;
  const url = URL.createObjectURL(file);
  visionPreview.src = url;
  visionPreview.style.display = 'block';
}

$('vision-analyze-btn').addEventListener('click', async () => {
  if (!visionFile) return showToast('Select an image first', 'err');
  const box = $('vision-result');
  box.textContent = 'Analyzing…';
  const fd = new FormData();
  fd.append('image', visionFile);
  const q = $('vision-question').value.trim();
  if (q) fd.append('question', q);
  try {
    const r = await fetch('/api/vision/analyze', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.analysis || data.error || 'No result';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('vision-ocr-btn').addEventListener('click', async () => {
  if (!visionFile) return showToast('Select an image first', 'err');
  const box = $('vision-result');
  box.textContent = 'Extracting text…';
  const fd = new FormData();
  fd.append('image', visionFile);
  try {
    const r = await fetch('/api/vision/ocr', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.text || data.error || 'No text found';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('vision-url-btn').addEventListener('click', async () => {
  const url = $('vision-url').value.trim();
  if (!url) return showToast('Enter image URL', 'err');
  const box = $('vision-url-result');
  box.textContent = 'Analyzing…';
  try {
    const r = await APIJ('/api/vision/analyze', { url, question: $('vision-url-question').value.trim() });
    const data = await r.json();
    box.textContent = data.analysis || data.error || 'No result';
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

/* ═══════════════════════════════════════
   TAB 6 — DATA ANALYSIS
═══════════════════════════════════════ */
let dataFile = null;
const dataArea = $('data-upload-area');
const dataInput = $('data-file-input');

dataArea.addEventListener('click', () => dataInput.click());
dataArea.addEventListener('dragover', e => { e.preventDefault(); dataArea.classList.add('dragover'); });
dataArea.addEventListener('dragleave', () => dataArea.classList.remove('dragover'));
dataArea.addEventListener('drop', e => {
  e.preventDefault();
  dataArea.classList.remove('dragover');
  if (e.dataTransfer.files[0]) { dataFile = e.dataTransfer.files[0]; dataArea.querySelector('span').textContent = `📊 ${dataFile.name}`; }
});
dataInput.addEventListener('change', () => {
  if (dataInput.files[0]) { dataFile = dataInput.files[0]; dataArea.querySelector('span').textContent = `📊 ${dataFile.name}`; }
});

$('data-analyze-btn').addEventListener('click', async () => {
  if (!dataFile) return showToast('Select a CSV or Excel file', 'err');
  const box = $('data-result');
  box.textContent = 'Analyzing…';
  const fd = new FormData();
  fd.append('file', dataFile);
  const q = $('data-question').value.trim();
  if (q) fd.append('question', q);
  try {
    const r = await fetch('/api/data/analyze', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.answer || data.error || JSON.stringify(data);
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('data-summary-btn').addEventListener('click', async () => {
  if (!dataFile) return showToast('Select a CSV or Excel file', 'err');
  const box = $('data-result');
  box.textContent = 'Loading…';
  const fd = new FormData();
  fd.append('file', dataFile);
  try {
    const r = await fetch('/api/data/upload', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    box.textContent = data.summary || data.error || JSON.stringify(data);
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('chart-btn').addEventListener('click', async () => {
  if (!dataFile) return showToast('Select a CSV or Excel file', 'err');
  const resultDiv = $('chart-result');
  resultDiv.innerHTML = '<p style="color:var(--muted)">Generating chart…</p>';
  const fd = new FormData();
  fd.append('file', dataFile);
  fd.append('chart_type', $('chart-type').value);
  fd.append('x_col', $('chart-x').value.trim());
  fd.append('y_col', $('chart-y').value.trim());
  try {
    const r = await fetch('/api/data/chart', { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    if (data.url) {
      resultDiv.innerHTML = `<img src="${data.url}" alt="chart" />`;
    } else {
      resultDiv.textContent = data.error || JSON.stringify(data);
    }
  } catch (e) { resultDiv.textContent = `Error: ${e.message}`; }
});

/* ═══════════════════════════════════════
   TAB 7 — PERSONAS
═══════════════════════════════════════ */
$('refresh-personas-btn').addEventListener('click', loadPersonas);

async function loadPersonas() {
  try {
    const r = await API('/api/personas');
    const { personas } = await r.json();
    const grid = $('personas-list');
    grid.innerHTML = personas.map(p => `
      <div class="persona-card" onclick="selectPersona('${p.id}')">
        <div class="p-emoji">${p.emoji || '🤖'}</div>
        <div class="p-name">${escHtml(p.name)}</div>
        <div class="p-desc">${escHtml(p.description || '')}</div>
        ${p.builtin ? '' : `<button class="btn danger small p-badge" onclick="deletePersona(event,'${p.id}')">Delete</button>`}
      </div>`).join('');

    const sel = $('persona-select');
    const existingValues = [...sel.options].map(o => o.value);
    personas.filter(p => !p.builtin && !existingValues.includes(p.id)).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.emoji || '🤖'} ${p.name}`;
      sel.appendChild(opt);
    });
  } catch { }
}

function selectPersona(id) {
  $('persona-select').value = id;
  document.querySelector('[data-tab="chat"]').click();
  showToast(`Persona selected: ${id}`, 'ok');
}

async function deletePersona(evt, id) {
  evt.stopPropagation();
  const r = await fetch(`/api/personas/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  const data = await r.json();
  if (data.deleted) { showToast('Deleted', 'ok'); loadPersonas(); }
  else showToast(data.error || 'Error', 'err');
}

$('persona-create-btn').addEventListener('click', async () => {
  const pid = $('persona-id').value.trim();
  const name = $('persona-name').value.trim();
  const emoji = $('persona-emoji').value.trim() || '🤖';
  const desc = $('persona-desc').value.trim();
  const system = $('persona-system').value.trim();
  if (!pid || !name || !system) return showToast('ID, name, and system prompt are required', 'err');
  const r = await APIJ('/api/personas', { id: pid, name, description: desc, system, emoji });
  const data = await r.json();
  $('persona-create-result').textContent = data.id ? `✅ Created: ${data.name}` : JSON.stringify(data);
  if (data.id) { loadPersonas(); $('persona-id').value = ''; $('persona-name').value = ''; $('persona-system').value = ''; }
});

loadPersonas();

/* ═══════════════════════════════════════
   TAB 8 — PROMPT TEMPLATES
═══════════════════════════════════════ */
$('refresh-templates-btn').addEventListener('click', loadTemplates);

async function loadTemplates() {
  try {
    const r = await API('/api/templates');
    const { templates } = await r.json();
    const list = $('templates-list');
    list.innerHTML = templates.map(t => `
      <div class="template-card">
        <div class="tmpl-info">
          <div class="tmpl-name">${escHtml(t.name)}</div>
          <div class="tmpl-desc">${escHtml(t.description || '')}</div>
          <div class="tmpl-vars">Variables: ${(t.variables || []).map(v => `{{${v}}}`).join(', ')}</div>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn secondary small" onclick="selectTemplate('${t.id}')">Use</button>
          ${t.builtin ? '' : `<button class="btn danger small" onclick="deleteTemplate('${t.id}')">Delete</button>`}
        </div>
      </div>`).join('');

    const sel = $('template-select');
    sel.innerHTML = '<option value="">— Select a template —</option>' +
      templates.map(t => `<option value="${t.id}">${escHtml(t.name)}</option>`).join('');
  } catch { }
}

function selectTemplate(id) {
  $('template-select').value = id;
  buildTemplateVarsForm(id);
}

$('template-select').addEventListener('change', () => {
  buildTemplateVarsForm($('template-select').value);
});

async function buildTemplateVarsForm(id) {
  if (!id) { $('template-vars-form').innerHTML = ''; return; }
  try {
    const r = await API(`/api/templates/${id}`);
    const t = await r.json();
    $('template-vars-form').innerHTML = (t.variables || []).map(v =>
      `<div><label style="color:var(--muted);font-size:13px;display:block;margin-bottom:4px">{{${v}}}</label>
       <input type="text" id="tvar-${v}" placeholder="${v}" /></div>`
    ).join('');
  } catch { }
}

$('template-run-btn').addEventListener('click', async () => {
  const id = $('template-select').value;
  if (!id) return showToast('Select a template', 'err');
  const vars = collectTemplateVars();
  const box = $('template-result');
  box.textContent = 'Running…';
  try {
    const r = await APIJ(`/api/templates/${id}/run`, { variables: vars });
    const data = await r.json();
    box.textContent = data.output || data.error || JSON.stringify(data);
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('template-preview-btn').addEventListener('click', async () => {
  const id = $('template-select').value;
  if (!id) return showToast('Select a template', 'err');
  const vars = collectTemplateVars();
  try {
    const r = await APIJ(`/api/templates/${id}/render`, { variables: vars });
    const data = await r.json();
    $('template-result').textContent = data.rendered || data.error || JSON.stringify(data);
  } catch (e) { $('template-result').textContent = `Error: ${e.message}`; }
});

function collectTemplateVars() {
  const vars = {};
  document.querySelectorAll('#template-vars-form input').forEach(inp => {
    const key = inp.id.replace('tvar-', '');
    vars[key] = inp.value;
  });
  return vars;
}

$('new-tmpl-btn').addEventListener('click', async () => {
  const name = $('new-tmpl-name').value.trim();
  const tmpl = $('new-tmpl-text').value.trim();
  const desc = $('new-tmpl-desc').value.trim();
  if (!name || !tmpl) return showToast('Name and template body are required', 'err');
  const r = await APIJ('/api/templates', { name, template: tmpl, description: desc });
  const data = await r.json();
  $('new-tmpl-result').textContent = data.id ? `✅ Saved: ${data.name}` : JSON.stringify(data);
  if (data.id) { loadTemplates(); $('new-tmpl-name').value = ''; $('new-tmpl-text').value = ''; }
});

async function deleteTemplate(id) {
  const r = await fetch(`/api/templates/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  const data = await r.json();
  if (data.deleted) { showToast('Deleted', 'ok'); loadTemplates(); }
  else showToast(data.error || 'Error', 'err');
}

loadTemplates();

/* ═══════════════════════════════════════
   TAB 9 — BATCH
═══════════════════════════════════════ */
$('batch-run-btn').addEventListener('click', async () => {
  const lines = $('batch-input').value.trim().split('\n').map(l => l.trim()).filter(Boolean);
  if (!lines.length) return showToast('Enter at least one task', 'err');
  const box = $('batch-result');
  const btn = $('batch-run-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Running… <span class="spinner"></span>';
  box.textContent = `Running ${lines.length} tasks in parallel…`;
  try {
    const body = { tasks: lines };
    const model = getActiveModel();
    if (model) body.model = model;
    const r = await APIJ('/api/batch', body);
    const data = await r.json();
    if (data.error) { box.textContent = `Error: ${data.error}`; return; }
    box.innerHTML = `<strong>✅ ${data.completed} completed | ❌ ${data.failed} failed</strong>\n\n` +
      data.results.map((res, i) =>
        `--- Task ${i + 1} [${res.status}] ---\n${res.task}\n\n${res.output || res.error || ''}`
      ).join('\n\n═══════════════════\n\n');
  } catch (e) { box.textContent = `Error: ${e.message}`; }
  finally { btn.disabled = false; btn.textContent = '▶ Run All'; }
});

/* ═══════════════════════════════════════
   TAB 10 — SCHEDULER
═══════════════════════════════════════ */
$('sched-add-btn').addEventListener('click', async () => {
  const name = $('sched-name').value.trim();
  const task = $('sched-task').value.trim();
  const cron = $('sched-cron').value.trim();
  if (!name || !task || !cron) return showToast('All fields are required', 'err');
  const r = await APIJ('/api/scheduler/jobs', { name, task, cron });
  const data = await r.json();
  $('sched-result').textContent = data.id ? `✅ Scheduled: ${data.id}` : JSON.stringify(data);
  $('sched-name').value = ''; $('sched-task').value = ''; $('sched-cron').value = '';
  loadJobs();
});

$('refresh-sched-btn').addEventListener('click', loadJobs);

async function loadJobs() {
  try {
    const r = await API('/api/scheduler/jobs');
    const { jobs } = await r.json();
    const list = $('sched-list');
    if (!jobs.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No scheduled jobs</p>'; return; }
    list.innerHTML = jobs.map(j => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">⏰ ${escHtml(j.name)} — <code style="font-size:12px">${escHtml(j.cron)}</code></span>
          <span class="task-time">${j.next_run ? 'Next: ' + j.next_run : ''}</span>
          <button class="btn danger small" onclick="deleteJob('${j.id}')">Delete</button>
        </div>
        <div style="color:var(--muted);font-size:13px;margin-top:4px">${escHtml(j.task).slice(0, 80)}</div>
      </div>`).join('');
  } catch { }
}

async function deleteJob(id) {
  await fetch(`/api/scheduler/jobs/${id}`, { method: 'DELETE', headers: getAuthHeader() });
  loadJobs();
}

loadJobs();

/* ═══════════════════════════════════════
   TAB 11 — MODELS
═══════════════════════════════════════ */
async function loadModels() {
  const grid = $('models-grid');
  const status = $('models-status');
  grid.innerHTML = '<p style="color:var(--muted)">Loading models…</p>';
  try {
    const r = await API('/api/models');
    const data = await r.json();
    const { claude = [], local = [], ollama_available = false, current_model = '' } = data;

    status.textContent = ollama_available
      ? `✅ Ollama connected — ${local.length} local model(s) available`
      : '⚠️ Ollama not running — only Claude models available';

    const activeModel = getActiveModel() || current_model;
    let html = '';

    if (claude.length) {
      html += `<div style="grid-column:1/-1;color:var(--muted);font-size:12px;margin-top:4px">── Claude (Anthropic) ──</div>`;
      html += claude.map(m => `
        <div class="model-card ${activeModel === m.id ? 'active-model' : ''}">
          <div class="m-name">${escHtml(m.name || m.id)}</div>
          <div class="m-provider">Anthropic</div>
          <div class="m-size">${escHtml(m.description || '')}</div>
          <div class="m-actions">
            <button class="btn secondary small" onclick="useModel('${escHtml(m.id)}')">Use</button>
          </div>
        </div>`).join('');
    }

    if (local.length) {
      html += `<div style="grid-column:1/-1;color:var(--muted);font-size:12px;margin-top:8px">── Local (Ollama) ──</div>`;
      html += local.map(m => `
        <div class="model-card ${activeModel === m.name ? 'active-model' : ''}">
          <div class="m-name">${escHtml(m.name)}</div>
          <div class="m-provider">Local / Ollama</div>
          <div class="m-size">${m.size ? (m.size / 1e9).toFixed(1) + ' GB' : ''}</div>
          <div class="m-actions">
            <button class="btn secondary small" onclick="useModel('${escHtml(m.name)}')">Use</button>
            <button class="btn danger small" onclick="deleteLocalModel('${escHtml(m.name)}')">Delete</button>
          </div>
        </div>`).join('');
    }

    if (!claude.length && !local.length) {
      html = '<p style="color:var(--muted)">No models found. Check your API key and Ollama status.</p>';
    }

    grid.innerHTML = html;
    loadAllModelSelects(data);
  } catch (e) {
    grid.textContent = `Error: ${e.message}`;
  }
}

function useModel(modelId) {
  setActiveModel(modelId);
  showToast(`Active model: ${modelId}`, 'ok');
  loadModels();
}

async function deleteLocalModel(name) {
  if (!confirm(`Delete local model "${name}"?`)) return;
  try {
    const r = await APIJ('/api/models/delete', { name });
    const data = await r.json();
    if (data.deleted) { showToast(`Deleted: ${name}`, 'ok'); loadModels(); }
    else showToast(data.error || 'Delete failed', 'err');
  } catch (e) { showToast(`Error: ${e.message}`, 'err'); }
}

function loadAllModelSelects(data) {
  const { claude = [], local = [], current_model = '' } = data || {};
  const activeModel = getActiveModel() || current_model;

  const buildOptions = () => {
    let opts = '<option value="">Default (config)</option>';
    if (claude.length) {
      opts += `<optgroup label="Claude Models">`;
      opts += claude.map(m => `<option value="${escHtml(m.id)}">${escHtml(m.name || m.id)}</option>`).join('');
      opts += `</optgroup>`;
    }
    if (local.length) {
      opts += `<optgroup label="Local (Ollama)">`;
      opts += local.map(m => `<option value="${escHtml(m.name)}">${escHtml(m.name)}</option>`).join('');
      opts += `</optgroup>`;
    }
    return opts;
  };

  const gSel = $('global-model-select');
  const cSel = $('chat-model-select');
  const opts = buildOptions();
  if (gSel) { gSel.innerHTML = opts; if (activeModel) gSel.value = activeModel; }
  if (cSel) { cSel.innerHTML = opts; if (activeModel) cSel.value = activeModel; }
}

/* Pull a local model via SSE */
$('pull-model-btn').addEventListener('click', pullModel);

async function pullModel() {
  const customVal = $('pull-model-custom').value.trim();
  const selectVal = $('pull-model-select').value;
  const modelName = customVal || selectVal;
  if (!modelName) return showToast('Select or type a model name', 'err');

  const box = $('pull-result');
  const btn = $('pull-model-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Pulling… <span class="spinner"></span>';
  box.textContent = `Pulling ${modelName}…\n`;

  try {
    const res = await fetch('/api/models/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
      body: JSON.stringify({ name: modelName }),
    });

    if (!res.ok) {
      const err = await res.json();
      box.textContent = `Error: ${err.error || res.statusText}`;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const text = line.slice(6);
          if (text && text !== '[DONE]') {
            box.textContent += text + '\n';
            box.scrollTop = box.scrollHeight;
          }
        }
      }
    }
    showToast(`✅ ${modelName} pulled successfully`, 'ok');
    loadModels();
  } catch (e) {
    box.textContent += `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Pull';
  }
}

/* Global model select change handler */
$('global-model-select').addEventListener('change', () => {
  const val = $('global-model-select').value;
  setActiveModel(val);
  if (val) showToast(`Active model: ${val}`, 'ok');
});

$('refresh-models-btn').addEventListener('click', loadModels);

/* Load models on startup to populate selects */
(async () => {
  try {
    const r = await API('/api/models');
    const data = await r.json();
    loadAllModelSelects(data);
  } catch { }
})();

/* ═══════════════════════════════════════
   TAB 12 — MONITORING
═══════════════════════════════════════ */
$('refresh-stats-btn').addEventListener('click', loadMonitoring);

async function loadMonitoring() {
  try {
    const [statsR, reqR, hourR] = await Promise.all([
      API('/api/monitoring/stats'),
      API('/api/monitoring/requests?n=30'),
      API('/api/monitoring/hourly'),
    ]);
    const stats = await statsR.json();
    const { requests } = await reqR.json();
    const { hourly } = await hourR.json();

    $('stats-grid').innerHTML = [
      { label: 'Total Requests', value: stats.total_requests },
      { label: 'Input Tokens', value: (stats.total_input_tokens || 0).toLocaleString() },
      { label: 'Output Tokens', value: (stats.total_output_tokens || 0).toLocaleString() },
      { label: 'Cost (USD)', value: `$${(stats.total_cost_usd || 0).toFixed(4)}` },
      { label: 'Errors', value: stats.errors || 0 },
    ].map(s => `
      <div class="stat-card">
        <div class="stat-value">${escHtml(String(s.value))}</div>
        <div class="stat-label">${s.label}</div>
      </div>`).join('');

    $('requests-list').textContent = requests.map(r =>
      `[${r.ts.slice(11, 19)}] ${r.endpoint} — ${r.input_tokens}↑${r.output_tokens}↓ — $${r.cost_usd} — ${r.latency_ms}ms${r.error ? ' ❌' : ''}`
    ).join('\n');

    $('hourly-list').textContent = hourly.map(h =>
      `${h.hour}: ${h.requests} requests | ${h.tokens} tokens | $${h.cost.toFixed(4)}`
    ).join('\n') || 'No data yet';
  } catch (e) { $('stats-grid').textContent = `Error: ${e.message}`; }
}

/* ═══════════════════════════════════════
   TAB — MULTI-AGENT SYSTEM
═══════════════════════════════════════ */
async function loadAgentsGrid() {
  try {
    const r = await API('/api/agents');
    const { agents } = await r.json();
    $('agents-grid').innerHTML = agents.map(a => `
      <div class="agent-card">
        <div class="a-emoji">${a.emoji || '🤖'}</div>
        <div class="a-name">${escHtml(a.name)}</div>
        <div class="a-desc">${escHtml(a.description)}</div>
      </div>`).join('');
  } catch { }
}

async function loadAgentHistory() {
  try {
    const r = await API('/api/agents/history');
    const { history } = await r.json();
    const list = $('agent-history');
    if (!history.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No team runs yet</p>'; return; }
    list.innerHTML = history.map(h => `
      <div class="task-card">
        <div class="task-head">
          <span class="task-text">${escHtml(h.task)}</span>
          <span class="task-time">${h.ts}</span>
          <span class="badge running">${h.mode}</span>
        </div>
        <div style="color:var(--muted);font-size:12px;margin-top:4px">
          Agents: ${h.agents.join(', ')}
        </div>
      </div>`).join('');
  } catch { }
}

$('agent-run-btn').addEventListener('click', async () => {
  const task = $('agent-task-input').value.trim();
  const mode = $('agent-mode-select').value;
  if (!task) return showToast('Enter a task', 'err');

  const btn = $('agent-run-btn');
  const box = $('agent-output');
  btn.disabled = true;
  btn.innerHTML = '⏳ Team working… <span class="spinner"></span>';
  box.textContent = '';

  try {
    const res = await fetch('/api/agents/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
      body: JSON.stringify({ task, mode }),
    });

    if (!res.ok) {
      const err = await res.json();
      box.textContent = `Error: ${err.error || res.statusText}`;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          const text = line.slice(6).replace(/\\n/g, '\n');
          box.textContent += text;
          box.scrollTop = box.scrollHeight;
        }
      }
    }
    loadAgentHistory();
    showToast('✅ Team task complete', 'ok');
  } catch (e) {
    box.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Run Team';
  }
});

$('refresh-agent-history-btn').addEventListener('click', loadAgentHistory);

document.querySelector('[data-tab="agents"]').addEventListener('click', () => {
  loadAgentsGrid();
  loadAgentHistory();
});

/* ═══════════════════════════════════════
   TAB — VOICE
═══════════════════════════════════════ */
let voiceAudioBlob = null;
let voiceMediaRecorder = null;
let voiceChunks = [];

async function checkVoiceStatus() {
  try {
    const r = await API('/api/voice/status');
    const data = await r.json();
    $('voice-status').textContent = data.whisper_available
      ? `✅ Whisper available — models: ${data.models.join(', ')}`
      : '⚠️ Whisper not installed. Run: pip install openai-whisper';
  } catch (e) {
    $('voice-status').textContent = `Status check failed: ${e.message}`;
  }
}

const voiceArea = $('voice-upload-area');
const voiceFileInput = $('voice-file-input');
voiceArea.addEventListener('click', () => voiceFileInput.click());
voiceArea.addEventListener('dragover', e => { e.preventDefault(); voiceArea.classList.add('dragover'); });
voiceArea.addEventListener('dragleave', () => voiceArea.classList.remove('dragover'));
voiceArea.addEventListener('drop', e => {
  e.preventDefault();
  voiceArea.classList.remove('dragover');
  if (e.dataTransfer.files[0]) {
    voiceAudioBlob = e.dataTransfer.files[0];
    voiceArea.querySelector('span').textContent = `🎵 ${voiceAudioBlob.name}`;
  }
});
voiceFileInput.addEventListener('change', () => {
  if (voiceFileInput.files[0]) {
    voiceAudioBlob = voiceFileInput.files[0];
    voiceArea.querySelector('span').textContent = `🎵 ${voiceAudioBlob.name}`;
  }
});

async function _doTranscribe(runAsTask = false) {
  if (!voiceAudioBlob) return showToast('Select or record an audio file first', 'err');
  const box = runAsTask ? $('voice-result') : $('voice-result');
  box.textContent = 'Transcribing…';

  const fd = new FormData();
  fd.append('audio', voiceAudioBlob, voiceAudioBlob.name || 'audio.wav');
  const lang = $('voice-language').value.trim();
  if (lang) fd.append('language', lang);
  fd.append('model', $('voice-model-select').value);

  const endpoint = runAsTask ? '/api/voice/transcribe-and-run' : '/api/voice/transcribe';
  try {
    const r = await fetch(endpoint, { method: 'POST', body: fd, headers: getAuthHeader() });
    const data = await r.json();
    if (data.error) { box.textContent = `Error: ${data.error}`; return; }

    if (runAsTask) {
      box.textContent = `[Transcription] ${data.transcription?.text || ''}\n\n[Task Output]\n${data.output || ''}`;
    } else {
      const segs = (data.segments || []).map(s =>
        `[${s.start.toFixed(1)}s → ${s.end.toFixed(1)}s] ${s.text}`).join('\n');
      box.textContent = `Language: ${data.language || 'auto'}\n\n${data.text}\n\n${segs ? 'Segments:\n' + segs : ''}`;
    }
  } catch (e) { box.textContent = `Error: ${e.message}`; }
}

$('voice-transcribe-btn').addEventListener('click', () => _doTranscribe(false));
$('voice-run-btn').addEventListener('click', () => _doTranscribe(true));

// Browser microphone recording
$('voice-record-btn').addEventListener('click', async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    voiceChunks = [];
    voiceMediaRecorder = new MediaRecorder(stream);
    voiceMediaRecorder.ondataavailable = e => voiceChunks.push(e.data);
    voiceMediaRecorder.onstop = () => {
      const blob = new Blob(voiceChunks, { type: 'audio/webm' });
      voiceAudioBlob = new File([blob], 'recording.webm', { type: 'audio/webm' });
      const url = URL.createObjectURL(blob);
      const playback = $('voice-playback');
      playback.src = url;
      playback.style.display = 'block';
      $('voice-record-result').textContent = '✅ Recording ready — click Transcribe above';
      stream.getTracks().forEach(t => t.stop());
    };
    voiceMediaRecorder.start();
    $('voice-record-btn').disabled = true;
    $('voice-stop-btn').disabled = false;
    $('voice-record-result').textContent = '⏺ Recording…';
  } catch (e) {
    showToast(`Microphone access denied: ${e.message}`, 'err');
  }
});

$('voice-stop-btn').addEventListener('click', () => {
  if (voiceMediaRecorder && voiceMediaRecorder.state !== 'inactive') {
    voiceMediaRecorder.stop();
    $('voice-record-btn').disabled = false;
    $('voice-stop-btn').disabled = true;
  }
});

document.querySelector('[data-tab="voice"]').addEventListener('click', checkVoiceStatus);

/* ═══════════════════════════════════════
   TAB — AUTOMATION
═══════════════════════════════════════ */
$('briefing-btn').addEventListener('click', async () => {
  const btn = $('briefing-btn');
  const box = $('briefing-result');
  btn.disabled = true;
  btn.innerHTML = '⏳ Generating… <span class="spinner"></span>';
  box.textContent = 'Fetching news and generating briefing…';
  try {
    const note = $('briefing-note').value.trim();
    const r = await APIJ('/api/automation/briefing', { note });
    const data = await r.json();
    if (data.error) { box.textContent = `Error: ${data.error}`; return; }
    box.textContent = `${data.briefing}\n\n[Generated: ${data.generated_at}]`;
  } catch (e) { box.textContent = `Error: ${e.message}`; }
  finally { btn.disabled = false; btn.textContent = 'Generate Briefing'; }
});

async function loadResources() {
  try {
    const r = await API('/api/system/resources');
    const d = await r.json();

    const cards = [
      { label: 'CPU', value: `${d.cpu_percent}%`, warn: d.cpu_percent > 75, err: d.cpu_percent > 90 },
      { label: 'RAM', value: `${d.memory_percent}%`, warn: d.memory_percent > 75, err: d.memory_percent > 90 },
      { label: 'Disk', value: `${d.disk_percent}%`, warn: d.disk_percent > 80, err: d.disk_percent > 90 },
      { label: 'RAM Used', value: `${d.memory_used_gb} GB` },
      { label: 'Disk Used', value: `${d.disk_used_gb} GB` },
      { label: 'Net ↑', value: `${d.net_sent_mb} MB` },
    ];

    $('resources-grid').innerHTML = cards.map(c => `
      <div class="resource-card${c.err ? ' err' : c.warn ? ' warn' : ''}">
        <div class="res-value">${c.value}</div>
        <div class="res-label">${c.label}</div>
      </div>`).join('');

    $('top-processes').textContent = 'Top processes:\n' +
      (d.top_processes || []).map(p =>
        `${p.name.padEnd(18)} CPU: ${String(p.cpu).padStart(5)}%  MEM: ${String(p.mem).padStart(5)}%  PID: ${p.pid}`
      ).join('\n');
  } catch (e) { $('resources-grid').textContent = `Error: ${e.message}`; }
}

async function updateMonitorStatus() {
  try {
    const r = await API('/api/system/monitor');
    const d = await r.json();
    $('monitor-status').textContent =
      d.running
        ? `✅ Monitor running (every ${d.interval_s}s) | notify-send: ${d.notify_send_available ? '✅' : '❌ not installed'}`
        : `⏹ Monitor stopped | notify-send: ${d.notify_send_available ? '✅' : '❌ not installed'}`;
  } catch { }
}

$('refresh-resources-btn').addEventListener('click', loadResources);

$('monitor-start-btn').addEventListener('click', async () => {
  await APIJ('/api/system/monitor/start', { interval_s: 60 });
  updateMonitorStatus();
  showToast('Resource monitor started', 'ok');
});

$('monitor-stop-btn').addEventListener('click', async () => {
  await APIJ('/api/system/monitor/stop', {});
  updateMonitorStatus();
  showToast('Monitor stopped', 'ok');
});

async function runMaintenance(dryRun) {
  const action = $('maintenance-action').value;
  const box = $('maintenance-result');
  box.textContent = dryRun ? 'Running dry run…' : 'Running cleanup…';
  try {
    const r = await APIJ('/api/automation/maintenance', { action, dry_run: dryRun });
    const data = await r.json();
    if (data.error) { box.textContent = `Error: ${data.error}`; return; }

    const lines = [];
    const addSection = (title, result) => {
      if (!result) return;
      lines.push(`── ${title} ──`);
      if (result.removed_count !== undefined)
        lines.push(`Removed: ${result.removed_count} items (${result.total_freed_mb} MB freed)`);
      if (result.root)
        lines.push(`Disk: ${result.root.used_gb}/${result.root.total_gb} GB (${result.root.percent}%)`);
      if (result.error) lines.push(`Error: ${result.error}`);
    };

    if (data.temp_cleanup) addSection('Temp Files', data.temp_cleanup);
    if (data.log_cleanup) addSection('Old Logs', data.log_cleanup);
    if (data.disk_report) addSection('Disk Report', data.disk_report);
    if (data.removed_count !== undefined) addSection(action, data);

    box.textContent = lines.join('\n') || JSON.stringify(data, null, 2);
    if (!dryRun) showToast('✅ Maintenance complete', 'ok');
  } catch (e) { box.textContent = `Error: ${e.message}`; }
}

$('maintenance-dry-btn').addEventListener('click', () => runMaintenance(true));
$('maintenance-run-btn').addEventListener('click', () => runMaintenance(false));

$('notif-send-btn').addEventListener('click', async () => {
  const title = $('notif-title').value.trim() || 'AI Agent';
  const body = $('notif-body').value.trim();
  if (!body) return showToast('Enter notification body', 'err');
  const urgency = $('notif-urgency').value;
  try {
    const r = await APIJ('/api/system/notify', { title, body, urgency });
    const data = await r.json();
    $('notif-result').textContent = data.sent
      ? `✅ Notification sent: "${title}" — ${body}`
      : `⚠️ notify-send not available (logged instead)`;
  } catch (e) { $('notif-result').textContent = `Error: ${e.message}`; }
});

document.querySelector('[data-tab="automation"]').addEventListener('click', () => {
  loadResources();
  updateMonitorStatus();
});

/* ═══════════════════════════════════════
   TAB — SELF-HEALING SYSTEM
═══════════════════════════════════════ */
$('heal-analyze-btn').addEventListener('click', () => runHealAnalysis(false));
$('heal-auto-btn').addEventListener('click', () => runHealAnalysis(true));

async function runHealAnalysis(autoApply) {
  const error = $('heal-error').value.trim();
  if (!error) return showToast('Paste an error traceback first', 'err');
  const task = $('heal-task').value.trim();
  const file = $('heal-file').value.trim();
  const box = $('heal-result');
  const btn = autoApply ? $('heal-auto-btn') : $('heal-analyze-btn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Analyzing… <span class="spinner"></span>';
  box.textContent = 'Sending error to healer…';

  try {
    const endpoint = autoApply ? '/api/heal/auto' : '/api/heal/analyze';
    const r = await APIJ(endpoint, { error, task, file });
    const data = await r.json();

    if (autoApply) {
      const patch = data.patch || {};
      const apply = data.apply_result || {};
      const healed = data.healed;
      box.textContent = [
        `Healed: ${healed ? '✅ YES' : '❌ NO'}`,
        `Analysis: ${patch.analysis || 'N/A'}`,
        `Confidence: ${((patch.confidence || 0) * 100).toFixed(0)}%`,
        `Safe to apply: ${patch.safe_to_apply}`,
        `File: ${patch.file || 'N/A'}`,
        apply.applied ? `✅ Patch applied → backup: ${apply.backup}` : `⚠️ Not applied: ${apply.reason || apply.error || 'N/A'}`,
      ].join('\n');
      if (healed) showToast('✅ Self-heal applied successfully', 'ok');
      else showToast('Patch proposed but not applied', 'ok');
    } else {
      box.textContent = [
        `Analysis: ${data.analysis || 'N/A'}`,
        `Confidence: ${((data.confidence || 0) * 100).toFixed(0)}%`,
        `Safe to apply: ${data.safe_to_apply}`,
        `Patch type: ${data.patch_type || 'N/A'}`,
        `File: ${data.file || 'N/A'}`,
        `Reasoning: ${data.reasoning || 'N/A'}`,
        data.old_code ? `\nOLD:\n${data.old_code}` : '',
        data.new_code ? `\nNEW:\n${data.new_code}` : '',
      ].filter(Boolean).join('\n');

      if (data.safe_to_apply && data.old_code) {
        const applyBtn = document.createElement('button');
        applyBtn.className = 'btn primary';
        applyBtn.textContent = '✅ Apply This Patch';
        applyBtn.style.marginTop = '10px';
        applyBtn.addEventListener('click', async () => {
          applyBtn.disabled = true;
          const r2 = await APIJ('/api/heal/apply', { patch: data });
          const d2 = await r2.json();
          box.textContent += `\n\nApply result: ${d2.applied ? '✅ Applied' : '❌ ' + (d2.error || d2.reason)}`;
          if (d2.applied) { loadHealLog(); showToast('✅ Patch applied', 'ok'); }
        });
        box.parentNode.insertBefore(applyBtn, box.nextSibling);
      }
    }
    loadHealLog();
  } catch (e) { box.textContent = `Error: ${e.message}`; }
  finally { btn.disabled = false; btn.innerHTML = btn === $('heal-auto-btn') ? '⚡ Analyze + Auto-Apply' : '🔍 Analyze'; }
}

async function loadHealLog() {
  try {
    const r = await API('/api/heal/log');
    const { log } = await r.json();
    const list = $('heal-log');
    if (!log.length) { list.innerHTML = '<p style="color:var(--muted);font-size:13px">No heals yet</p>'; return; }
    list.innerHTML = log.map(h => `
      <div class="heal-card ${h.applied ? '' : 'failed'}">
        <div class="heal-file">${escHtml(h.file || 'unknown file')}</div>
        <div class="heal-analysis">${escHtml(h.analysis || h.patch_summary || '')}</div>
        <div class="heal-meta">
          ${h.ts || ''} | confidence: ${((h.confidence || 0) * 100).toFixed(0)}%
          ${h.backup ? ` | <a href="#" class="link" onclick="restoreBackup('${escHtml(h.backup)}');return false">↩ Restore</a>` : ''}
        </div>
      </div>`).join('');
  } catch { }
}

async function restoreBackup(path) {
  if (!confirm(`Restore from backup?\n${path}`)) return;
  const r = await APIJ('/api/heal/restore', { backup_path: path });
  const data = await r.json();
  showToast(data.restored ? '✅ Restored' : '❌ Restore failed', data.restored ? 'ok' : 'err');
}

$('refresh-heal-log-btn').addEventListener('click', loadHealLog);
$('refresh-backups-btn').addEventListener('click', async () => {
  const r = await API('/api/heal/backups');
  const { backups } = await r.json();
  $('heal-log').innerHTML = backups.length
    ? backups.map(b => `<div class="heal-card"><div class="heal-file">${escHtml(b.name)}</div><div class="heal-meta">${b.ts} | ${(b.size/1024).toFixed(1)} KB | <a href="#" class="link" onclick="restoreBackup('${escHtml(b.path)}');return false">↩ Restore</a></div></div>`).join('')
    : '<p style="color:var(--muted);font-size:13px">No backups</p>';
});

document.querySelector('[data-tab="healer"]').addEventListener('click', loadHealLog);

/* ═══════════════════════════════════════
   TAB — DIGITAL TWIN
═══════════════════════════════════════ */
let _currentProbeQuestion = '';

$('twin-name-btn').addEventListener('click', async () => {
  const name = $('twin-name').value.trim();
  if (!name) return showToast('Enter your name', 'err');
  await APIJ('/api/twin/name', { name });
  showToast(`Twin personalized for: ${name}`, 'ok');
});

$('twin-profile-btn').addEventListener('click', async () => {
  const box = $('twin-summary');
  box.textContent = 'Loading profile…';
  try {
    const r = await API('/api/twin/profile');
    const data = await r.json();
    const profile = data.profile;
    const summary = data.summary;
    box.textContent = summary + (Object.keys(profile).length
      ? '\n\n── Profile fields ──\n' + Object.entries(profile).map(([k,v]) => `${k}: ${JSON.stringify(v).slice(0,80)}`).join('\n')
      : '\n\n(Profile empty — ingest some files to train the twin)');
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

// File ingestion
const twinArea = $('twin-upload-area');
const twinFileInput = $('twin-file-input');
twinArea.addEventListener('click', () => twinFileInput.click());
twinArea.addEventListener('dragover', e => { e.preventDefault(); twinArea.classList.add('dragover'); });
twinArea.addEventListener('dragleave', () => twinArea.classList.remove('dragover'));
twinArea.addEventListener('drop', async e => {
  e.preventDefault(); twinArea.classList.remove('dragover');
  if (e.dataTransfer.files.length) await ingestTwinFiles(e.dataTransfer.files);
});
twinFileInput.addEventListener('change', async () => { if (twinFileInput.files.length) await ingestTwinFiles(twinFileInput.files); });

$('twin-ingest-file-btn').addEventListener('click', async () => {
  if (twinFileInput.files.length) await ingestTwinFiles(twinFileInput.files);
  else twinFileInput.click();
});

async function ingestTwinFiles(files) {
  const box = $('twin-ingest-result');
  box.textContent = `Ingesting ${files.length} file(s)…`;
  let results = [];
  for (const f of files) {
    const fd = new FormData();
    fd.append('file', f);
    try {
      const r = await fetch('/api/twin/ingest/file', { method: 'POST', body: fd, headers: getAuthHeader() });
      const data = await r.json();
      results.push(`${f.name}: ${data.ok ? '✅' : '❌ ' + data.error}`);
    } catch (e) { results.push(`${f.name}: ❌ ${e.message}`); }
  }
  box.textContent = results.join('\n');
  showToast(`Twin trained on ${files.length} file(s)`, 'ok');
}

$('twin-ingest-dir-btn').addEventListener('click', async () => {
  const path = $('twin-dir').value.trim();
  if (!path) return showToast('Enter a directory path', 'err');
  const box = $('twin-ingest-result');
  box.textContent = `Ingesting directory: ${path}…`;
  try {
    const r = await APIJ('/api/twin/ingest/directory', { path });
    const data = await r.json();
    box.textContent = data.error
      ? `Error: ${data.error}`
      : `✅ Ingested ${data.ingested} files from ${path}`;
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

// Ask the twin (streaming)
$('twin-ask-btn').addEventListener('click', async () => {
  const question = $('twin-question').value.trim();
  if (!question) return showToast('Enter a question', 'err');
  const box = $('twin-answer');
  box.textContent = 'Your twin is thinking…';
  $('twin-ask-btn').disabled = true;

  try {
    const res = await fetch('/api/twin/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
      body: JSON.stringify({ question }),
    });
    box.textContent = '';
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          box.textContent += line.slice(6);
          box.scrollTop = box.scrollHeight;
        }
      }
    }
  } catch (e) { box.textContent = `Error: ${e.message}`; }
  finally { $('twin-ask-btn').disabled = false; $('twin-ask-btn').textContent = 'Ask Twin'; }
});

// Probing session
$('twin-probe-btn').addEventListener('click', async () => {
  const box = $('twin-probe-question');
  box.textContent = 'Generating question…';
  try {
    const r = await API('/api/twin/probe');
    const data = await r.json();
    _currentProbeQuestion = data.question;
    box.textContent = data.question;
  } catch (e) { box.textContent = `Error: ${e.message}`; }
});

$('twin-probe-submit-btn').addEventListener('click', async () => {
  const answer = $('twin-probe-answer').value.trim();
  if (!answer || !_currentProbeQuestion) return showToast('Generate a question and write your answer first', 'err');
  try {
    await APIJ('/api/twin/probe/answer', { question: _currentProbeQuestion, answer });
    $('twin-probe-result').textContent = '✅ Answer recorded — twin profile updated';
    $('twin-probe-answer').value = '';
    showToast('Twin learned from your answer', 'ok');
  } catch (e) { $('twin-probe-result').textContent = `Error: ${e.message}`; }
});

```

---

## `static/css/main.css`

```css
:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --surface2: #22263a;
  --accent: #6c63ff;
  --accent2: #4fd1c5;
  --text: #e2e8f0;
  --muted: #8892a4;
  --border: #2d3352;
  --ok: #48bb78;
  --warn: #ed8936;
  --err: #fc8181;
  --radius: 10px;
  --shadow: 0 4px 24px rgba(0,0,0,.4);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Segoe UI', system-ui, sans-serif;
  font-size: 15px;
  min-height: 100vh;
  direction: rtl;
}

/* NAV */
.navbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
  flex-wrap: wrap;
}
.nav-brand {
  font-size: 20px;
  font-weight: 700;
  color: var(--accent);
  white-space: nowrap;
}
.nav-tabs { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.nav-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.tab-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--muted);
  padding: 6px 16px;
  border-radius: 20px;
  cursor: pointer;
  font-size: 14px;
  transition: all .2s;
}
.tab-btn:hover { border-color: var(--accent); color: var(--text); }
.tab-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.health-dot {
  width: 11px; height: 11px;
  border-radius: 50%;
  background: var(--muted);
  transition: background .4s;
  flex-shrink: 0;
}
.health-dot.ok { background: var(--ok); box-shadow: 0 0 6px var(--ok); }
.health-dot.err { background: var(--err); }

/* TABS */
.tab-content { display: none; padding: 24px; max-width: 1100px; margin: 0 auto; }
.tab-content.active { display: block; }

/* PANEL */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: var(--shadow);
}
.panel h2 {
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--accent2);
}

/* INPUTS */
textarea, input[type="text"] {
  width: 100%;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 10px 14px;
  font-size: 14px;
  outline: none;
  transition: border .2s;
  margin-bottom: 12px;
  font-family: inherit;
  direction: rtl;
}
textarea:focus, input[type="text"]:focus { border-color: var(--accent); }
textarea { resize: vertical; min-height: 80px; }

.input-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.input-row input { margin-bottom: 0; flex: 1; }

.btn-row { display: flex; gap: 10px; margin-bottom: 16px; }

/* BUTTONS */
.btn {
  padding: 9px 22px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: all .2s;
  white-space: nowrap;
}
.btn.primary { background: var(--accent); color: #fff; }
.btn.primary:hover { background: #7c74ff; }
.btn.primary:disabled { background: #444; cursor: not-allowed; }
.btn.secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
.btn.secondary:hover { border-color: var(--accent); color: var(--accent); }
.btn.small { padding: 5px 12px; font-size: 13px; }
.btn.danger { background: var(--err); color: #fff; }

/* OUTPUT BOX */
.output-box {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  min-height: 80px;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  direction: ltr;
  text-align: left;
}
.output-box:empty::before { content: "النتيجة ستظهر هنا…"; color: var(--muted); font-family: inherit; }

/* TASKS LIST */
.tasks-list { display: flex; flex-direction: column; gap: 10px; }
.task-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: border .2s;
}
.task-card:hover { border-color: var(--accent); }
.task-card .task-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.task-card .task-text { color: var(--text); font-size: 14px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-card .task-time { color: var(--muted); font-size: 12px; white-space: nowrap; margin-right: 10px; }
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}
.badge.pending { background: #3d3720; color: var(--warn); }
.badge.running { background: #1e2d5a; color: #63b3ed; }
.badge.completed { background: #1a3329; color: var(--ok); }
.badge.failed { background: #3d1a1a; color: var(--err); }

/* CHAT */
.chat-panel { display: flex; flex-direction: column; height: calc(100vh - 130px); }
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.msg {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user { background: var(--accent); color: #fff; align-self: flex-end; border-bottom-right-radius: 4px; direction: rtl; }
.msg.assistant { background: var(--surface2); color: var(--text); align-self: flex-start; border-bottom-left-radius: 4px; direction: ltr; text-align: left; }
.msg.typing { color: var(--muted); font-style: italic; }
.chat-input-row {
  display: flex;
  gap: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.chat-input-row input { margin-bottom: 0; flex: 1; }

/* UPLOAD */
.upload-area {
  border: 2px dashed var(--border);
  border-radius: 10px;
  padding: 32px;
  text-align: center;
  color: var(--muted);
  transition: border .2s;
  cursor: pointer;
  margin-bottom: 12px;
}
.upload-area:hover, .upload-area.dragover { border-color: var(--accent); color: var(--text); }
.link { color: var(--accent); cursor: pointer; text-decoration: underline; }

/* SCROLLBAR */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* LOADING SPINNER */
@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  display: inline-block;
  width: 16px; height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .6s linear infinite;
  vertical-align: middle;
  margin-left: 8px;
}

/* MARKDOWN-LIKE in output */
.output-box strong { color: var(--accent2); }
.output-box code { background: rgba(255,255,255,.08); padding: 1px 5px; border-radius: 4px; }

/* IMAGE PREVIEW */
.image-preview {
  max-width: 100%;
  max-height: 260px;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  display: block;
}

/* CHART RESULT */
#chart-result img {
  max-width: 100%;
  border-radius: 8px;
  margin-top: 12px;
  border: 1px solid var(--border);
}

/* PERSONAS GRID */
.personas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.persona-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  text-align: center;
  cursor: pointer;
  transition: border .2s, transform .2s;
}
.persona-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.persona-card .p-emoji { font-size: 32px; margin-bottom: 8px; }
.persona-card .p-name { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.persona-card .p-desc { color: var(--muted); font-size: 12px; }
.persona-card .p-badge { margin-top: 8px; }

/* FORM GRID */
.form-grid { display: flex; flex-direction: column; gap: 10px; }
.form-grid input, .form-grid textarea, .form-grid select { margin-bottom: 0; }

/* SELECT */
select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 10px 14px;
  font-size: 14px;
  outline: none;
  width: 100%;
  margin-bottom: 12px;
  cursor: pointer;
}
select:focus { border-color: var(--accent); }

/* STATS GRID */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.stat-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}
.stat-card .stat-value { font-size: 24px; font-weight: 700; color: var(--accent); }
.stat-card .stat-label { color: var(--muted); font-size: 12px; margin-top: 4px; }

/* TEMPLATES LIST */
.templates-list { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.template-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.template-card .tmpl-info .tmpl-name { font-weight: 600; margin-bottom: 3px; }
.template-card .tmpl-info .tmpl-desc { color: var(--muted); font-size: 12px; }
.template-card .tmpl-info .tmpl-vars { color: var(--accent2); font-size: 11px; margin-top: 3px; }

/* HINT */
.hint { color: var(--muted); font-size: 13px; margin-bottom: 12px; }

/* CHAT PERSONA ROW */
.chat-persona-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
.chat-persona-row label { color: var(--muted); white-space: nowrap; }
.chat-persona-row select { margin-bottom: 0; flex: 0 0 220px; }

/* TOAST */
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 24px;
  font-size: 14px;
  transition: transform .3s;
  z-index: 9999;
  pointer-events: none;
}
.toast.show { transform: translateX(-50%) translateY(0); }

/* MODELS GRID */
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.model-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  transition: border .2s;
}
.model-card.active-model { border-color: var(--accent); }
.model-card .m-name { font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.model-card .m-provider { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
.model-card .m-size { color: var(--accent2); font-size: 11px; }
.model-card .m-actions { margin-top: 8px; display: flex; gap: 6px; }

/* CHAT TOP ROW */
.chat-top-row {
  display: flex;
  align-items: center;
  gap: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.chat-persona-row, .chat-model-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.chat-persona-row label, .chat-model-row label { color: var(--muted); white-space: nowrap; font-size: 13px; }
.chat-persona-row select, .chat-model-row select { margin-bottom: 0; width: auto; }

/* GLOBAL MODEL SELECT IN NAVBAR */
#global-model-select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 5px 10px;
  font-size: 12px;
  outline: none;
  cursor: pointer;
  max-width: 180px;
}
#global-model-select:focus { border-color: var(--accent); }

/* AGENT CARDS */
.agent-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}
.agent-card .a-emoji { font-size: 28px; margin-bottom: 6px; }
.agent-card .a-name { font-weight: 700; font-size: 14px; margin-bottom: 4px; color: var(--accent); }
.agent-card .a-desc { color: var(--muted); font-size: 12px; }

/* AGENT OUTPUT — preserves newlines + colors phase headers */
#agent-output { white-space: pre-wrap; direction: ltr; text-align: left; }

/* RESOURCE CARDS */
.resource-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
}
.resource-card .res-value { font-size: 22px; font-weight: 700; color: var(--accent2); }
.resource-card .res-label { color: var(--muted); font-size: 12px; margin-top: 4px; }
.resource-card.warn .res-value { color: var(--warn); }
.resource-card.err  .res-value { color: var(--err); }

/* VOICE UPLOAD */
#voice-upload-area { margin-bottom: 0; }

/* HEAL LOG */
.heal-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--ok);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 8px;
  font-size: 13px;
}
.heal-card.failed { border-left-color: var(--err); }
.heal-card .heal-file { color: var(--accent2); font-weight: 600; }
.heal-card .heal-analysis { color: var(--text); margin-top: 4px; }
.heal-card .heal-meta { color: var(--muted); font-size: 12px; margin-top: 4px; }

/* TWIN PROFILE */
#twin-summary { white-space: pre-wrap; direction: ltr; text-align: left; }
#twin-answer  { white-space: pre-wrap; direction: ltr; text-align: left; }
.twin-upload-area { margin-bottom: 10px; }

```

---

## `scripts/setup.sh`

```sh
#!/usr/bin/env bash
# setup.sh — One-liner remote installer for AI Agent
#
# Usage (run directly from GitHub):
#   curl -fsSL https://raw.githubusercontent.com/abusultancom/-ai-agent/main/scripts/setup.sh | bash
#
# Or with a custom install directory:
#   curl -fsSL .../setup.sh | INSTALL_DIR=/opt/ai-agent bash

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/abusultancom/-ai-agent.git"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.ai-agent}"
BRANCH="${BRANCH:-main}"
MIN_PYTHON="3.10"

# ── Colors ────────────────────────────────────────────────────────────────────
R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"
C="\033[96m"; W="\033[97m"; D="\033[2m"; BOLD="\033[1m"; RESET="\033[0m"

banner() {
  echo -e "${C}${BOLD}"
  echo '  █████╗ ██╗    █████╗  ██████╗ ███████╗███╗   ██╗████████╗'
  echo ' ██╔══██╗██║   ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝'
  echo ' ███████║██║   ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   '
  echo ' ██╔══██║██║   ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   '
  echo ' ██║  ██║██║   ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   '
  echo ' ╚═╝  ╚═╝╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   '
  echo -e "${RESET}${D}  AI Agent — Installer${RESET}"
  echo ""
}

info()    { echo -e "${B}[•]${RESET} $*"; }
ok()      { echo -e "${G}[✓]${RESET} $*"; }
warn()    { echo -e "${Y}[!]${RESET} $*"; }
fail()    { echo -e "${R}[✗]${RESET} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${W}── $* ──${RESET}"; }

# ── Prerequisite checks ───────────────────────────────────────────────────────
check_prereqs() {
  step "Checking prerequisites"

  # python3
  if ! command -v python3 &>/dev/null; then
    warn "python3 not found — attempting to install…"
    if command -v apt-get &>/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
      sudo dnf install -y python3 python3-pip
    elif command -v brew &>/dev/null; then
      brew install python3
    else
      fail "Cannot install python3 automatically. Please install Python 3.10+ and re-run."
    fi
  fi

  # version check
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_OK=$(python3 -c "import sys; print(int(sys.version_info >= (3,10)))")
  if [[ "$PY_OK" != "1" ]]; then
    fail "Python $MIN_PYTHON+ required (found $PY_VER). Please upgrade Python."
  fi
  ok "Python $PY_VER"

  # git
  if ! command -v git &>/dev/null; then
    warn "git not found — attempting to install…"
    if command -v apt-get &>/dev/null; then
      sudo apt-get install -y -qq git
    elif command -v dnf &>/dev/null; then
      sudo dnf install -y git
    elif command -v brew &>/dev/null; then
      brew install git
    else
      fail "Cannot install git automatically. Please install git and re-run."
    fi
  fi
  ok "git $(git --version | awk '{print $3}')"

  # pip
  if ! python3 -m pip --version &>/dev/null; then
    warn "pip not found — attempting to install…"
    python3 -m ensurepip --upgrade 2>/dev/null || \
      curl -fsSL https://bootstrap.pypa.io/get-pip.py | python3
  fi
  ok "pip $(python3 -m pip --version | awk '{print $2}')"

  # curl (needed if script was piped, but let's verify)
  command -v curl &>/dev/null && ok "curl available" || warn "curl not found (continuing anyway)"
}

# ── Clone or update repo ──────────────────────────────────────────────────────
clone_or_update() {
  step "Fetching repository"

  if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Repository already exists at $INSTALL_DIR — updating…"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH" --quiet
    git -C "$INSTALL_DIR" checkout "$BRANCH" --quiet
    git -C "$INSTALL_DIR" pull origin "$BRANCH" --quiet
    ok "Repository updated"
  else
    info "Cloning $REPO_URL → $INSTALL_DIR"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR" --quiet
    ok "Repository cloned"
  fi
}

# ── Install Python dependencies ───────────────────────────────────────────────
install_deps() {
  step "Installing Python dependencies"
  cd "$INSTALL_DIR"

  # Optional: use a venv if not already in one
  if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ "${USE_VENV:-1}" == "1" ]]; then
    if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
      info "Creating virtual environment…"
      python3 -m venv "$INSTALL_DIR/.venv"
    fi
    # shellcheck source=/dev/null
    source "$INSTALL_DIR/.venv/bin/activate"
    ok "Virtual environment active"
  fi

  info "Running pip install…"
  python3 -m pip install -q -r requirements.txt
  ok "Dependencies installed"
}

# ── Configure .env ────────────────────────────────────────────────────────────
configure_env() {
  step "Configuration"
  cd "$INSTALL_DIR"

  if [[ ! -f ".env" ]]; then
    cp .env.example .env
    info "Created .env from template"
  else
    info ".env already exists — skipping creation"
  fi

  # Always run the interactive config wizard
  info "Launching configuration wizard…"
  echo ""
  python3 scripts/ai-config --first-run
}

# ── Install system service and CLI tools ──────────────────────────────────────
install_service() {
  step "System integration"
  cd "$INSTALL_DIR"

  if command -v systemctl &>/dev/null; then
    if [[ $EUID -ne 0 ]]; then
      info "Installing systemd service (requires sudo)…"
      sudo bash scripts/install.sh
    else
      bash scripts/install.sh
    fi
  else
    warn "systemd not available — skipping service installation"
    warn "To start manually: cd $INSTALL_DIR && python3 orchestrator.py serve"

    # Install CLI tools manually (no systemd path)
    if [[ $EUID -eq 0 ]]; then
      cp "$INSTALL_DIR/scripts/ai" /usr/local/bin/ai
      chmod +x /usr/local/bin/ai
      cp "$INSTALL_DIR/scripts/aish" /usr/local/bin/aish
      chmod +x /usr/local/bin/aish
      cp "$INSTALL_DIR/scripts/ai-config" /usr/local/bin/ai-config
      chmod +x /usr/local/bin/ai-config
      ok "CLI tools installed → /usr/local/bin/{ai,aish,ai-config}"
    else
      info "Skipping global CLI install (not root)"
      info "Add $INSTALL_DIR/scripts to your PATH to use ai/aish/ai-config"
    fi
  fi
}

# ── Done ──────────────────────────────────────────────────────────────────────
print_summary() {
  PORT=$(grep -E '^PORT=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "5000")
  PORT="${PORT:-5000}"

  echo ""
  echo -e "${G}${BOLD}╔══════════════════════════════════════════════╗${RESET}"
  echo -e "${G}${BOLD}║        AI Agent installed successfully!      ║${RESET}"
  echo -e "${G}${BOLD}╚══════════════════════════════════════════════╝${RESET}"
  echo ""
  echo -e "  ${BOLD}Dashboard${RESET}  →  http://localhost:${PORT}"
  echo -e "  ${BOLD}CLI${RESET}        →  ai \"your task here\""
  echo -e "  ${BOLD}AI Shell${RESET}   →  aish"
  echo -e "  ${BOLD}Configure${RESET}  →  ai-config"
  echo -e "  ${BOLD}Logs${RESET}       →  ai logs"
  echo -e "  ${BOLD}Restart${RESET}    →  sudo systemctl restart ai-agent"
  echo ""
  echo -e "  ${D}Install dir: $INSTALL_DIR${RESET}"
  echo ""
}

# ── Entry point ───────────────────────────────────────────────────────────────
main() {
  clear 2>/dev/null || true
  banner

  check_prereqs
  clone_or_update
  install_deps
  configure_env
  install_service
  print_summary
}

main "$@"

```

---

## `scripts/install.sh`

```sh
#!/usr/bin/env bash
# install.sh — installs AI Agent as a persistent systemd service
# Usage: sudo bash scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="ai-agent"
SERVICE_FILE="$REPO_DIR/ai-agent.service"
SYSTEMD_DIR="/etc/systemd/system"
CLI_BIN="/usr/local/bin/ai"

# ── Checks ──────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "❌  Run as root:  sudo bash scripts/install.sh" >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "❌  python3 not found" >&2; exit 1
fi

if ! command -v systemctl &>/dev/null; then
  echo "❌  systemd not available on this system" >&2; exit 1
fi

# ── .env check ──────────────────────────────────────────────────────────────
if [[ ! -f "$REPO_DIR/.env" ]]; then
  echo "⚠️   No .env found — launching configuration wizard…"
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  python3 "$REPO_DIR/scripts/ai-config" --first-run
fi

# ── Install Python deps ──────────────────────────────────────────────────────
echo "📦  Installing Python dependencies…"
python3 -m pip install -q -r "$REPO_DIR/requirements.txt"

# ── Patch service file with actual repo path ─────────────────────────────────
TMP_SERVICE=$(mktemp)
sed "s|/home/user/-ai-agent|$REPO_DIR|g" "$SERVICE_FILE" > "$TMP_SERVICE"

# Set User= to current calling user (whoever ran sudo)
REAL_USER="${SUDO_USER:-root}"
sed -i "s|^User=.*|User=$REAL_USER|" "$TMP_SERVICE"

# ── Install service ──────────────────────────────────────────────────────────
echo "🔧  Installing systemd unit…"
cp "$TMP_SERVICE" "$SYSTEMD_DIR/$SERVICE_NAME.service"
rm "$TMP_SERVICE"
chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME.service"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# ── Install CLI wrappers ─────────────────────────────────────────────────────
echo "🔗  Installing CLI tools…"
cp "$REPO_DIR/scripts/ai" "$CLI_BIN"
chmod +x "$CLI_BIN"

cp "$REPO_DIR/scripts/aish" "/usr/local/bin/aish"
chmod +x "/usr/local/bin/aish"

cp "$REPO_DIR/scripts/ai-config" "/usr/local/bin/ai-config"
chmod +x "/usr/local/bin/ai-config"

echo "    → /usr/local/bin/ai        (CLI task runner)"
echo "    → /usr/local/bin/aish      (AI Shell)"
echo "    → /usr/local/bin/ai-config (configuration manager)"

# ── Done ────────────────────────────────────────────────────────────────────
sleep 1
STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "unknown")
PORT=$(grep -E '^PORT=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo "5000")
PORT="${PORT:-5000}"

if [[ "$STATUS" == "active" ]]; then
  echo ""
  echo "✅  AI Agent service is running!"
  echo "    Dashboard  : http://localhost:${PORT}"
  echo "    CLI        : ai \"your task here\""
  echo "    AI Shell   : aish"
  echo "    Configure  : ai-config"
  echo "    Logs       : ai logs  (or: journalctl -u ai-agent -f)"
  echo "    Stop       : sudo systemctl stop ai-agent"
else
  echo ""
  echo "⚠️   Service status: $STATUS"
  echo "    Check logs: journalctl -u $SERVICE_NAME -n 40"
fi

```

---

## `scripts/uninstall.sh`

```sh
#!/usr/bin/env bash
# uninstall.sh — removes the AI Agent systemd service and CLI wrapper
# Usage: sudo bash scripts/uninstall.sh

set -euo pipefail

SERVICE_NAME="ai-agent"
SYSTEMD_DIR="/etc/systemd/system"
CLI_BIN="/usr/local/bin/ai"

if [[ $EUID -ne 0 ]]; then
  echo "❌  Run as root:  sudo bash scripts/uninstall.sh" >&2
  exit 1
fi

echo "🛑  Stopping and disabling $SERVICE_NAME…"
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true

if [[ -f "$SYSTEMD_DIR/$SERVICE_NAME.service" ]]; then
  rm "$SYSTEMD_DIR/$SERVICE_NAME.service"
  echo "🗑️   Removed $SYSTEMD_DIR/$SERVICE_NAME.service"
fi

systemctl daemon-reload

if [[ -f "$CLI_BIN" ]]; then
  rm "$CLI_BIN"
  echo "🗑️   Removed $CLI_BIN"
fi

echo "✅  AI Agent service uninstalled. Data and config files are untouched."

```

---

## `docker-compose.yml`

```yml
version: '3.9'

services:
  ai-agent:
    build: .
    ports:
      - "5000:5000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - MODEL=${MODEL:-claude-opus-4-7}
      - SECRET_KEY=${SECRET_KEY:-change-me}
      - CHROMADB_PATH=/app/data/chromadb
      - DEBUG=${DEBUG:-false}
    volumes:
      - agent_data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  agent_data:

```

---

## `requirements.txt`

```txt
# Core LLM
anthropic>=0.92.0

# Web framework
flask>=3.0.0
flask-limiter>=3.5.0

# Config
python-dotenv>=1.0.0

# Memory / Vector DB
chromadb>=0.5.0

# Web tools
requests>=2.31.0
beautifulsoup4>=4.12.0

# Browser automation (optional — for screenshots)
playwright>=1.40.0

# PDF parsing (optional — for RAG)
pdfplumber>=0.10.0
pypdf>=4.0.0

# Task scheduling
apscheduler>=3.10.0

# Data validation
pydantic>=2.0.0

# Data analysis & charts
matplotlib>=3.8.0
openpyxl>=3.1.0
pandas>=2.0.0

# Excel parsing
xlrd>=2.0.0

# Notifications
slack-sdk>=3.27.0

# System resource monitoring (desktop notifications + resource monitor)
psutil>=5.9.0

# Voice interface — Whisper STT (install separately if needed)
# openai-whisper>=20231117   # uncomment to install Whisper
# pyttsx3>=2.90              # optional TTS engine

# RSS feed parsing (morning briefing)
lxml>=4.9.0

```

---

## `.env.example`

```env
# ── Required ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ── Core ──────────────────────────────────────────────────────────────────────
MODEL=claude-opus-4-7
SECRET_KEY=change-me-in-production
CHROMADB_PATH=./data/chromadb
MAX_TOKENS=16000
MAX_AGENT_ITERATIONS=30
BASH_TIMEOUT=30
WEB_TIMEOUT=15
DEBUG=false
HOST=0.0.0.0
PORT=5000

# ── Auth ──────────────────────────────────────────────────────────────────────
ADMIN_USER=admin
ADMIN_PASS=admin123
AUTH_DISABLED=true   # set false to require JWT on all API routes

# ── GitHub Integration ────────────────────────────────────────────────────────
GITHUB_TOKEN=ghp_...

# ── Email Notifications (SMTP) ────────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASS=your-app-password
SMTP_FROM=your@email.com
NOTIFY_EMAIL=     # auto-email on task completion (leave blank to disable)

# ── Slack Integration ─────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_BOT_TOKEN=xoxb-...

# ── Discord Integration ───────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=     # postgresql://user:pass@host/db (leave blank for SQLite)

# ── Local Models (Ollama) ─────────────────────────────────────────────────────
OLLAMA_URL=http://localhost:11434
LOCAL_MODEL=llama3.2   # default local model when no model is specified

```

---

## `README.md`

```markdown
# AI Agent

A production-grade autonomous AI agent powered by **Claude Opus 4.7** with an agentic tool-use loop, full web dashboard, local model support via Ollama, and OS-level system service integration.

---

## Features

| Category | Features |
|---|---|
| **Core AI** | Agentic task loop (30 iterations), extended thinking, prompt caching |
| **Local Models** | Ollama integration — run llama3.2, mistral, qwen, deepseek locally |
| **Model Routing** | Automatic Claude ↔ Ollama routing by model name prefix |
| **Chat** | Multi-turn chat with personas, per-session history, model selector |
| **Memory** | Persistent vector memory (ChromaDB), semantic search |
| **RAG** | Upload documents (PDF/TXT/MD/code), ask questions against them |
| **Vision** | Image analysis, OCR, URL-based image analysis (Claude Vision) |
| **Data Analysis** | CSV/Excel analysis with AI, chart generation (matplotlib) |
| **Personas** | 8 built-in + custom personas (Developer, Analyst, Writer, …) |
| **Templates** | Prompt templates with `{{variable}}` substitution |
| **Batch Tasks** | Parallel execution of multiple tasks (ThreadPoolExecutor) |
| **Scheduler** | Cron-based task scheduling (APScheduler) |
| **Monitoring** | Token usage, cost tracking, request logs, hourly summaries |
| **Auth** | JWT authentication (optional, HMAC-HS256) |
| **Rate Limiting** | Per-IP token-bucket rate limiting |
| **Database** | SQLite by default, PostgreSQL supported |
| **Browser** | Playwright browser automation for web tasks |
| **Code Sandbox** | Safe Python execution with import blocklist |
| **API Testing** | Built-in HTTP client for testing external APIs |
| **Notifications** | Email (SMTP), Slack, Discord webhooks |
| **Docker** | Full docker-compose setup |
| **System Service** | systemd integration — runs as a persistent OS service |

---

## Architecture

```
-ai-agent/
├── core/
│   ├── app.py              # Flask REST API (40+ endpoints)
│   ├── orchestrator.py     # Agentic Claude loop (tool-use, 30 iter)
│   ├── chat.py             # Multi-turn chat with session history
│   ├── config.py           # All settings via .env
│   ├── local_models.py     # Ollama client (list/pull/delete/chat)
│   ├── model_router.py     # Routes Claude vs Ollama by model name
│   ├── personas.py         # Built-in + custom personas
│   └── monitoring.py       # Usage and cost tracking
├── agents/
│   ├── planner_agent.py    # Task decomposition (Claude)
│   ├── executor_agent.py   # Step-by-step tool dispatch
│   └── memory_agent.py     # Memory store/recall/summarize
├── tools/
│   ├── llm_tools.py        # generate, stream, classify, summarize
│   ├── os_tools.py         # Safe bash execution with blocklist
│   ├── web_tools.py        # HTTP fetch + BeautifulSoup
│   ├── file_tools.py       # read, write, search, list
│   ├── db_tools.py         # SQL query sandbox
│   ├── vision_tools.py     # Image analysis (Claude Vision)
│   ├── data_tools.py       # CSV/Excel + chart generation
│   ├── browser_tools.py    # Playwright browser automation
│   └── code_sandbox.py     # Safe Python execution
├── memory/
│   ├── chromadb_client.py  # ChromaDB persistent vector store
│   └── memory_manager.py   # High-level memory interface
├── templates/index.html    # Web dashboard (12 tabs)
├── static/
│   ├── css/main.css
│   └── js/main.js
├── ai-agent.service        # systemd unit file
├── scripts/
│   ├── install.sh          # OS service installer
│   ├── uninstall.sh        # Service removal
│   └── ai                  # System-wide CLI wrapper
├── orchestrator.py         # CLI entry point
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/abusultancom/-ai-agent.git ai-agent
cd ai-agent
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure

Edit `.env` and set your API key:

```env
ANTHROPIC_API_KEY=sk-ant-...
MODEL=claude-opus-4-7
```

### 3. Run

```bash
# Web server + dashboard
python orchestrator.py serve
# Dashboard at http://localhost:5000

# Run a single task from CLI
python orchestrator.py run "Write a Python script that counts words in a file"

# Show task plan only (no execution)
python orchestrator.py plan "Build a REST API for a todo list"
```

---

## Install as a System Service (Linux)

Run the agent as a **persistent systemd service** that starts on boot and restarts automatically on failure.

```bash
# Install and start the service
sudo bash scripts/install.sh

# Check status
systemctl status ai-agent

# View live logs
journalctl -u ai-agent -f
```

After installation a system-wide `ai` command is available from any directory:

```bash
ai "Summarize the latest commits in this repo"
ai chat "Explain the difference between RAG and fine-tuning"
ai status        # check if service is running
ai logs          # follow live logs
ai restart       # restart the service
ai stop          # stop the service
```

### Uninstall

```bash
sudo bash scripts/uninstall.sh
```

---

## Local Models (Ollama)

Run open-source LLMs locally — no API key required.

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a model

```bash
# Via terminal
ollama pull llama3.2

# Or via the dashboard: Models tab → Pull
```

### 3. Select a model

Pick any model from the **Models** tab or the navbar selector. All chat and task calls route automatically.

**Routing logic:**
- Model name starts with `claude-` → Anthropic API
- Anything else (e.g. `llama3.2`, `mistral`) → Ollama

```env
# .env
OLLAMA_URL=http://localhost:11434
LOCAL_MODEL=llama3.2
```

**Supported models to pull:**

| Model | Size | Best for |
|---|---|---|
| `llama3.2` | 3B | Fast general tasks |
| `llama3.1` | 8B | Balanced |
| `mistral` | 7B | Instruction following |
| `qwen2.5-coder` | 7B | Code generation |
| `deepseek-r1` | 7B | Reasoning |
| `phi4` | 14B | Microsoft — efficient |
| `gemma2` | 9B | Google — quality |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/task` | Submit async task → `task_id` |
| GET | `/api/task/<id>` | Poll task status + output |
| GET | `/api/task/<id>/stream` | SSE stream of task output |
| POST | `/api/task/run` | Synchronous task execution |
| GET | `/api/tasks` | List recent tasks |
| POST | `/api/chat` | Multi-turn chat |
| POST | `/api/chat/persona` | Chat with a specific persona |
| POST | `/api/chat/clear` | Clear session history |
| POST | `/api/memory` | Store a memory |
| POST | `/api/memory/search` | Semantic memory search |
| POST | `/api/rag/upload` | Upload a document |
| POST | `/api/rag/query` | Query uploaded documents |
| GET | `/api/rag/documents` | List documents |
| DELETE | `/api/rag/documents` | Delete a document |
| POST | `/api/vision/analyze` | Analyze image (file or URL) |
| POST | `/api/vision/ocr` | Extract text from image |
| POST | `/api/data/upload` | Upload CSV/Excel |
| POST | `/api/data/analyze` | AI analysis of data |
| POST | `/api/data/chart` | Generate a chart |
| GET | `/api/personas` | List personas |
| POST | `/api/personas` | Create persona |
| DELETE | `/api/personas/<id>` | Delete persona |
| GET | `/api/templates` | List templates |
| POST | `/api/templates` | Create template |
| POST | `/api/templates/<id>/run` | Run template |
| POST | `/api/templates/<id>/render` | Preview template |
| POST | `/api/batch` | Run tasks in parallel |
| POST | `/api/scheduler/jobs` | Schedule a cron job |
| GET | `/api/scheduler/jobs` | List scheduled jobs |
| DELETE | `/api/scheduler/jobs/<id>` | Delete a job |
| GET | `/api/models` | List all models (Claude + Ollama) |
| GET | `/api/models/local` | List local Ollama models |
| POST | `/api/models/pull` | Pull an Ollama model (SSE stream) |
| POST | `/api/models/delete` | Delete a local model |
| GET | `/api/monitoring/stats` | Usage statistics |
| GET | `/api/monitoring/requests` | Recent request log |
| GET | `/api/monitoring/hourly` | Hourly usage summary |
| POST | `/api/auth/login` | Get JWT token |
| POST | `/api/db/query` | Execute SQL query (sandboxed) |
| POST | `/api/browser/screenshot` | Capture webpage screenshot |
| POST | `/api/browser/extract` | Extract webpage content |

---

## Configuration

All settings are read from `.env` at startup.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Anthropic API key |
| `MODEL` | `claude-opus-4-7` | Default Claude model |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `LOCAL_MODEL` | `llama3.2` | Default local model |
| `SECRET_KEY` | `dev-secret-…` | JWT signing key |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `5000` | Server port |
| `DEBUG` | `false` | Flask debug mode |
| `MAX_TOKENS` | `16000` | Max tokens per response |
| `MAX_AGENT_ITERATIONS` | `30` | Max agentic loop steps |
| `BASH_TIMEOUT` | `30` | Shell command timeout (s) |
| `WEB_TIMEOUT` | `15` | HTTP fetch timeout (s) |
| `CHROMADB_PATH` | `./data/chromadb` | Vector store path |
| `AUTH_DISABLED` | `true` | Disable JWT auth |
| `ADMIN_USER` | `admin` | Admin username |
| `ADMIN_PASS` | `admin123` | Admin password |
| `DATABASE_URL` | SQLite | PostgreSQL connection string |
| `SMTP_HOST` | — | Email SMTP host |
| `SLACK_WEBHOOK_URL` | — | Slack notifications |
| `DISCORD_WEBHOOK_URL` | — | Discord notifications |

---

## Agent Tools

The agentic loop has access to these built-in tools:

| Tool | Description |
|---|---|
| `execute_bash` | Shell commands with timeout and safety blocklist |
| `read_file` | Read file contents |
| `write_file` | Write / append to files |
| `search_files` | Glob pattern file search |
| `web_fetch` | HTTP fetch with content extraction |
| `memory_store` | Persist information in ChromaDB |
| `memory_search` | Semantic search over stored memories |

---

## Security

- Bash commands blocked against a safety blocklist before execution
- SQL queries blocked for injection patterns (UNION SELECT, stacked queries, inline comments)
- Python sandbox blocks `os`, `subprocess`, `socket`, and other dangerous imports
- Rate limiting: token-bucket per IP address
- JWT authentication (disabled by default — enable with `AUTH_DISABLED=false`)
- Web fetch timeout prevents hung requests

---

## Docker

```bash
docker compose up --build
# Dashboard at http://localhost:5000
```

---

## Tech Stack

- **AI**: Anthropic Claude Opus 4.7, Ollama (local LLMs)
- **Backend**: Python 3.11+, Flask, APScheduler
- **Vector DB**: ChromaDB (cosine similarity)
- **Browser automation**: Playwright
- **Charts**: matplotlib
- **Auth**: HMAC-HS256 JWT
- **Frontend**: Vanilla JS, CSS custom properties
- **Infra**: systemd, Docker / docker-compose

```
