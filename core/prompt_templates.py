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
