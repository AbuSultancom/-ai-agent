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
