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
