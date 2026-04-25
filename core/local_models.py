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
