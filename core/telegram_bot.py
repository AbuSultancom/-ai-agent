"""Telegram bot — streaming responses, tool progress, commands, media, memory."""

import io
import logging
import re
import threading
import time
from collections import defaultdict

import requests

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_polling_thread: threading.Thread | None = None

# Per-chat conversation history (in-memory)
_histories: dict[int, list[dict]] = defaultdict(list)
_histories_lock = threading.Lock()
MAX_HISTORY = 20  # messages per chat

# Tool name → friendly emoji label
_TOOL_LABELS = {
    "execute_bash":       "⚙️ Running command",
    "execute_python":     "🐍 Running Python",
    "read_file":          "📂 Reading file",
    "write_file":         "💾 Writing file",
    "search_files":       "🔍 Searching files",
    "web_fetch":          "🌐 Fetching URL",
    "web_search":         "🔍 Searching web",
    "browser_screenshot": "📸 Taking screenshot",
    "browser_get_text":   "🌐 Reading page",
    "browser_click":      "🖱️ Clicking",
    "browser_fill_form":  "📝 Filling form",
    "memory_store":       "🧠 Saving memory",
    "memory_search":      "🧠 Searching memory",
    "doc_search":         "📄 Searching docs",
    "git":                "🔀 Git operation",
    "github":             "🐙 GitHub",
    "send_email":         "📧 Sending email",
}

_TOOL_RE = re.compile(r'\*\*\[(\w+)\]\*\*\s*`([^`]*)`')

# ── Telegram API helpers ───────────────────────────────────────────────────────

def _api(token: str, method: str, **kwargs) -> dict:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=kwargs, timeout=15,
        )
        return r.json()
    except Exception as e:
        logger.warning("Telegram API %s error: %s", method, e)
        return {"ok": False}


def _send(token: str, chat_id: int, text: str, reply_markup=None) -> int | None:
    """Send message, return message_id."""
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = _api(token, "sendMessage", **payload)
    if result.get("ok"):
        return result["result"]["message_id"]
    return None


def _edit(token: str, chat_id: int, msg_id: int, text: str, reply_markup=None) -> bool:
    """Edit an existing message."""
    payload = {
        "chat_id": chat_id,
        "message_id": msg_id,
        "text": text[:4096],
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = _api(token, "editMessageText", **payload)
    return result.get("ok", False)


def _typing(token: str, chat_id: int) -> None:
    _api(token, "sendChatAction", chat_id=chat_id, action="typing")


def _send_photo(token: str, chat_id: int, path: str, caption: str = "") -> None:
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "Markdown"},
                files={"photo": f},
                timeout=30,
            )
    except Exception as e:
        logger.warning("sendPhoto error: %s", e)


def _download_file(token: str, file_id: str) -> bytes | None:
    """Download a file from Telegram servers."""
    try:
        r = _api(token, "getFile", file_id=file_id)
        if not r.get("ok"):
            return None
        file_path = r["result"]["file_path"]
        resp = requests.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}",
            timeout=30,
        )
        return resp.content
    except Exception as e:
        logger.warning("Download error: %s", e)
        return None


def _inline_kb(chat_id: int) -> dict:
    """Quick-action inline keyboard shown after each reply."""
    return {
        "inline_keyboard": [[
            {"text": "🆕 New chat",    "callback_data": f"new:{chat_id}"},
            {"text": "🔄 Continue",    "callback_data": f"cont:{chat_id}"},
            {"text": "🧠 Memory",      "callback_data": f"mem:{chat_id}"},
        ]]
    }


# ── Conversation history helpers ───────────────────────────────────────────────

def _add_history(chat_id: int, role: str, content: str) -> None:
    with _histories_lock:
        _histories[chat_id].append({"role": role, "content": content})
        if len(_histories[chat_id]) > MAX_HISTORY:
            _histories[chat_id] = _histories[chat_id][-MAX_HISTORY:]


def _get_history(chat_id: int) -> list[dict]:
    with _histories_lock:
        return list(_histories[chat_id])


def _clear_history(chat_id: int) -> None:
    with _histories_lock:
        _histories[chat_id] = []


# ── Streaming agent reply ──────────────────────────────────────────────────────

def _stream_reply(token: str, chat_id: int, user_text: str) -> None:
    """Run the agent and stream the reply by editing one Telegram message."""
    _typing(token, chat_id)
    msg_id = _send(token, chat_id, "🤔 _Thinking…_")
    if not msg_id:
        return

    history = _get_history(chat_id)
    history.append({"role": "user", "content": user_text})

    text_buf = ""
    status_line = ""
    screenshot_paths = []
    last_edit = 0.0
    EDIT_INTERVAL = 0.8  # seconds between edits (Telegram rate limit safe)

    def _current_display() -> str:
        body = text_buf or ""
        if status_line:
            return f"{status_line}\n\n{body}" if body else status_line
        return body or "🤔 _Thinking…_"

    try:
        from core.orchestrator import AIOrchestrator
        orch = AIOrchestrator()

        for chunk in orch.run_with_messages(history):
            m = _TOOL_RE.match(chunk.strip())
            if m:
                tool_name = m.group(1)
                tool_args = m.group(2)[:60]

                if tool_name == "screenshot_image":
                    # Queue screenshot for sending after text reply
                    screenshot_paths.append(tool_args)
                    continue

                label = _TOOL_LABELS.get(tool_name, f"⚙️ {tool_name}")
                status_line = f"_{label}…_ `{tool_args}`"
            else:
                if status_line and chunk.strip():
                    status_line = ""  # clear status once real text arrives
                text_buf += chunk

            # Throttle edits to avoid Telegram rate limits
            now = time.time()
            if now - last_edit >= EDIT_INTERVAL:
                _edit(token, chat_id, msg_id, _current_display())
                last_edit = now

        # Final edit with inline keyboard
        final_text = text_buf.strip() or "_(no response)_"
        _edit(token, chat_id, msg_id, final_text, reply_markup=_inline_kb(chat_id))

        # Store in history
        _add_history(chat_id, "user", user_text)
        _add_history(chat_id, "assistant", final_text)

        # Send any screenshots
        for path in screenshot_paths:
            if path.startswith("/api/screenshots/"):
                shot_id = path.split("/")[-1]
                local_path = f"data/screenshots/shot_{shot_id}.png"
                _send_photo(token, chat_id, local_path, "📸 Screenshot")

    except Exception as exc:
        logger.exception("Telegram agent error")
        err = f"❌ Error: {exc}"
        _edit(token, chat_id, msg_id, err)


# ── Commands ───────────────────────────────────────────────────────────────────

_HELP_TEXT = """🤖 *AI Agent Bot*

*Commands:*
/start — Welcome message
/new — Start a new conversation
/help — Show this help
/model — Show active model
/memory — Show conversation length
/clear — Clear conversation history

*What I can do:*
• 💬 Chat & answer questions
• 🔍 Search the web in real-time
• 📸 Take screenshots of websites
• 🐍 Run Python & bash code
• 📂 Read & write files
• 🔀 Git operations
• 🌐 Browse websites
• 📄 Analyze uploaded files & images

_Send any message to get started!_"""


def _handle_command(token: str, chat_id: int, cmd: str) -> None:
    if cmd == "/start":
        _send(token, chat_id, "👋 *AI Agent* is ready!\n\n" + _HELP_TEXT)
    elif cmd == "/help":
        _send(token, chat_id, _HELP_TEXT)
    elif cmd in ("/new", "/clear"):
        _clear_history(chat_id)
        _send(token, chat_id, "🆕 New conversation started. What can I help you with?")
    elif cmd == "/model":
        from core.config import config
        _send(token, chat_id, f"🤖 Active model: `{config.MODEL}`")
    elif cmd == "/memory":
        n = len(_get_history(chat_id))
        _send(token, chat_id, f"🧠 Conversation has *{n}* messages in memory.")
    else:
        _send(token, chat_id, f"Unknown command: `{cmd}`\n\nUse /help to see available commands.")


# ── Media handling ─────────────────────────────────────────────────────────────

def _handle_photo(token: str, chat_id: int, message: dict) -> None:
    """Download photo and pass to agent for vision analysis."""
    caption = message.get("caption", "Describe this image in detail.")
    photos = message.get("photo", [])
    if not photos:
        return
    # Largest photo = last item
    file_id = photos[-1]["file_id"]
    _typing(token, chat_id)
    msg_id = _send(token, chat_id, "🖼️ _Analyzing image…_")

    data = _download_file(token, file_id)
    if not data:
        _edit(token, chat_id, msg_id, "❌ Could not download image.")
        return

    try:
        import base64
        from core import model_router
        from core.config import config
        img_b64 = base64.standard_b64encode(data).decode()
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
            {"type": "text", "text": caption},
        ]
        history = _get_history(chat_id)
        msgs = history + [{"role": "user", "content": user_content}]
        response = model_router.chat_with_tools(msgs, [], model=config.MODEL, system=None)
        reply = response.get("text", "") or "_(no description)_"
        _edit(token, chat_id, msg_id, reply, reply_markup=_inline_kb(chat_id))
        _add_history(chat_id, "user", f"[Image] {caption}")
        _add_history(chat_id, "assistant", reply)
    except Exception as exc:
        _edit(token, chat_id, msg_id, f"❌ Vision error: {exc}")


def _handle_document(token: str, chat_id: int, message: dict) -> None:
    """Download document, extract text, pass to agent."""
    doc = message.get("document", {})
    filename = doc.get("file_name", "file")
    file_id = doc.get("file_id")
    caption = message.get("caption", f"Analyze this file: {filename}")
    if not file_id:
        return

    _typing(token, chat_id)
    msg_id = _send(token, chat_id, f"📎 _Processing `{filename}`…_")
    data = _download_file(token, file_id)
    if not data:
        _edit(token, chat_id, msg_id, "❌ Could not download file.")
        return

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext == "pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        else:
            text = data.decode("utf-8", errors="replace")
        content = f"[File: {filename}]\n\n{text[:8000]}"
    except Exception as e:
        content = f"[File: {filename}] (parse error: {e})"

    prompt = f"{caption}\n\n{content}"
    _edit(token, chat_id, msg_id, f"📎 _Running agent on `{filename}`…_")

    # Re-use streaming reply
    _clear_display_and_stream(token, chat_id, msg_id, prompt)


def _handle_voice(token: str, chat_id: int, message: dict) -> None:
    """Transcribe voice message then pass to agent."""
    file_id = message.get("voice", {}).get("file_id")
    if not file_id:
        return
    _typing(token, chat_id)
    msg_id = _send(token, chat_id, "🎤 _Transcribing voice…_")
    data = _download_file(token, file_id)
    if not data:
        _edit(token, chat_id, msg_id, "❌ Could not download voice message.")
        return
    try:
        import whisper, tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(data)
            tmp = f.name
        model = whisper.load_model("base")
        result = model.transcribe(tmp)
        os.unlink(tmp)
        transcript = result.get("text", "").strip()
        if not transcript:
            _edit(token, chat_id, msg_id, "❌ Could not transcribe audio.")
            return
        _edit(token, chat_id, msg_id, f"🎤 _{transcript}_\n\n🤔 _Thinking…_")
        _clear_display_and_stream(token, chat_id, msg_id, transcript)
    except ImportError:
        _edit(token, chat_id, msg_id,
              "⚠️ Voice transcription requires Whisper.\n"
              "Install: `pip install openai-whisper`")
    except Exception as exc:
        _edit(token, chat_id, msg_id, f"❌ Transcription error: {exc}")


def _clear_display_and_stream(token: str, chat_id: int, msg_id: int, user_text: str) -> None:
    """Like _stream_reply but reuses an existing message_id."""
    history = _get_history(chat_id)
    history.append({"role": "user", "content": user_text})

    text_buf = ""
    status_line = ""
    last_edit = 0.0
    EDIT_INTERVAL = 0.8

    def _current_display() -> str:
        body = text_buf or ""
        if status_line:
            return f"{status_line}\n\n{body}" if body else status_line
        return body or "🤔 _Thinking…_"

    try:
        from core.orchestrator import AIOrchestrator
        orch = AIOrchestrator()
        for chunk in orch.run_with_messages(history):
            m = _TOOL_RE.match(chunk.strip())
            if m:
                tool_name = m.group(1)
                if tool_name == "screenshot_image":
                    continue
                label = _TOOL_LABELS.get(tool_name, f"⚙️ {tool_name}")
                status_line = f"_{label}…_ `{m.group(2)[:60]}`"
            else:
                if status_line and chunk.strip():
                    status_line = ""
                text_buf += chunk
            now = time.time()
            if now - last_edit >= EDIT_INTERVAL:
                _edit(token, chat_id, msg_id, _current_display())
                last_edit = now

        final_text = text_buf.strip() or "_(no response)_"
        _edit(token, chat_id, msg_id, final_text, reply_markup=_inline_kb(chat_id))
        _add_history(chat_id, "user", user_text)
        _add_history(chat_id, "assistant", final_text)
    except Exception as exc:
        logger.exception("Stream error")
        _edit(token, chat_id, msg_id, f"❌ Error: {exc}")


# ── Inline button callbacks ────────────────────────────────────────────────────

def _handle_callback(token: str, callback: dict) -> None:
    query_id = callback["id"]
    data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]

    _api(token, "answerCallbackQuery", callback_query_id=query_id)

    if data.startswith("new:"):
        _clear_history(chat_id)
        _send(token, chat_id, "🆕 New conversation started!")
    elif data.startswith("cont:"):
        _send(token, chat_id, "💬 Continue — what's next?")
    elif data.startswith("mem:"):
        n = len(_get_history(chat_id))
        _send(token, chat_id, f"🧠 *{n}* messages in memory.\n/clear to reset.")


# ── Message dispatcher ─────────────────────────────────────────────────────────

def _handle_message(token: str, chat_id_filter: str, message: dict) -> None:
    chat_id = message["chat"]["id"]
    if chat_id_filter and str(chat_id) != chat_id_filter:
        return

    text = message.get("text", "").strip()

    # Commands
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        threading.Thread(
            target=_handle_command, args=(token, chat_id, cmd), daemon=True
        ).start()
        return

    # Photo
    if "photo" in message:
        threading.Thread(
            target=_handle_photo, args=(token, chat_id, message), daemon=True
        ).start()
        return

    # Document
    if "document" in message:
        threading.Thread(
            target=_handle_document, args=(token, chat_id, message), daemon=True
        ).start()
        return

    # Voice
    if "voice" in message:
        threading.Thread(
            target=_handle_voice, args=(token, chat_id, message), daemon=True
        ).start()
        return

    # Plain text → agent
    if text:
        threading.Thread(
            target=_stream_reply, args=(token, chat_id, text), daemon=True
        ).start()


# ── Polling loop ───────────────────────────────────────────────────────────────

def _poll_loop(token: str, chat_id_filter: str) -> None:
    offset = 0
    logger.info("Telegram bot started (filter chat_id=%s)", chat_id_filter or "all")
    while not _stop_event.is_set():
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"],
                },
                timeout=40,
            )
            data = r.json()
            if not data.get("ok"):
                logger.warning("getUpdates error: %s", data)
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    _handle_message(token, chat_id_filter, update["message"])
                elif "callback_query" in update:
                    cb_chat = str(update["callback_query"]["message"]["chat"]["id"])
                    if not chat_id_filter or cb_chat == chat_id_filter:
                        threading.Thread(
                            target=_handle_callback,
                            args=(token, update["callback_query"]),
                            daemon=True,
                        ).start()

        except requests.exceptions.ReadTimeout:
            continue
        except Exception as exc:
            logger.warning("Poll error: %s", exc)
            time.sleep(5)


# ── Public API ─────────────────────────────────────────────────────────────────

def start(token: str, chat_id: str) -> bool:
    global _polling_thread
    if not token or not chat_id:
        return False
    if _polling_thread and _polling_thread.is_alive():
        return True
    _stop_event.clear()
    _polling_thread = threading.Thread(
        target=_poll_loop, args=(token, chat_id),
        daemon=True, name="telegram-poll",
    )
    _polling_thread.start()
    return True


def stop() -> None:
    _stop_event.set()
