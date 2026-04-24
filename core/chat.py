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
