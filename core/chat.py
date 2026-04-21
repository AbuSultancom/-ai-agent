"""Multi-turn chat with the AI agent — maintains conversation history per session."""

import logging
import threading
import uuid

import anthropic

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


def chat(message: str, session_id: str = "default", history: list[dict] | None = None,
         system_override: str | None = None) -> str:
    """Send a message and get a reply. Maintains history per session_id."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    if history is not None:
        messages = [m for m in history if m.get("role") in ("user", "assistant")]
    else:
        messages = _get_or_create(session_id)
        messages.append({"role": "user", "content": message})

    system_text = system_override or _CHAT_SYSTEM

    try:
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages[-40:],  # keep last 40 turns
        )
        reply = next((b.text for b in response.content if b.type == "text"), "")

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
