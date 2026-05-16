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
