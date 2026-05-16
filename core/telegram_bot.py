"""Telegram bot — long-polling loop that receives messages and replies via AI Agent."""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

_polling_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _send(token: str, chat_id: str | int, text: str) -> None:
    """Send a message back to a Telegram chat (splits if >4096 chars)."""
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)] if len(text) > 4000 else [text]
    for chunk in chunks:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                timeout=15,
            )
        except Exception as e:
            logger.warning("Telegram send error: %s", e)


def _typing(token: str, chat_id: str | int) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except Exception:
        pass


def _handle_message(token: str, message: dict) -> None:
    """Process one incoming Telegram message in a background thread."""
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    if not text or text.startswith("/start"):
        if text.startswith("/start"):
            _send(token, chat_id,
                  "👋 *AI Agent* is connected!\n\nSend me any message and I'll respond using the full agent with all tools.")
        return

    def _run():
        _typing(token, chat_id)
        try:
            from core.orchestrator import AIOrchestrator
            orch = AIOrchestrator()
            chunks = []
            for chunk in orch.run_with_messages(
                [{"role": "user", "content": text}]
            ):
                # Skip tool-call markers in Telegram output
                if chunk.startswith("\n\n**[") and "`" in chunk:
                    continue
                chunks.append(chunk)
                # Send typing action every ~20 chunks so Telegram shows activity
                if len(chunks) % 20 == 0:
                    _typing(token, chat_id)
            reply = "".join(chunks).strip() or "_(no response)_"
            _send(token, chat_id, reply)
        except Exception as exc:
            logger.exception("Telegram agent error")
            _send(token, chat_id, f"❌ Error: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def _poll_loop(token: str, chat_id_filter: str) -> None:
    """Long-polling loop — runs in background thread."""
    offset = 0
    logger.info("Telegram polling started (token=...%s)", token[-6:])
    while not _stop_event.is_set():
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                timeout=40,
            )
            data = r.json()
            if not data.get("ok"):
                logger.warning("Telegram getUpdates error: %s", data)
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message")
                if not message:
                    continue
                incoming_chat = str(message["chat"]["id"])
                # Only respond to the configured chat (security)
                if chat_id_filter and incoming_chat != chat_id_filter:
                    logger.info("Ignoring message from chat %s (not allowed)", incoming_chat)
                    continue
                _handle_message(token, message)

        except requests.exceptions.ReadTimeout:
            continue  # normal — long-poll timeout
        except Exception as exc:
            logger.warning("Telegram poll error: %s", exc)
            time.sleep(5)


def start(token: str, chat_id: str) -> bool:
    """Start the polling loop in a daemon thread. Returns True if started."""
    global _polling_thread
    if not token or not chat_id:
        return False
    if _polling_thread and _polling_thread.is_alive():
        return True  # already running

    _stop_event.clear()
    _polling_thread = threading.Thread(
        target=_poll_loop, args=(token, chat_id), daemon=True, name="telegram-poll"
    )
    _polling_thread.start()
    return True


def stop() -> None:
    _stop_event.set()
