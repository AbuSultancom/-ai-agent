import logging
from collections.abc import Generator

import anthropic

from core.config import config

logger = logging.getLogger(__name__)


class LLMTools:
    """Wrappers around the Anthropic Claude API for common LLM operations."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = config.MODEL

    def generate(self, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        messages = [{"role": "user", "content": prompt}]
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {"type": "adaptive"},
        }
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        response = self.client.messages.create(**kwargs)
        return next((b.text for b in response.content if b.type == "text"), "")

    def stream(
        self, prompt: str, system: str = "", max_tokens: int = 16000
    ) -> Generator[str, None, None]:
        messages = [{"role": "user", "content": prompt}]
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {"type": "adaptive"},
        }
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    def classify(self, text: str, categories: list[str]) -> str:
        cats = ", ".join(categories)
        prompt = f"Classify the following text into exactly one of these categories: {cats}\n\nText: {text}\n\nRespond with only the category name."
        return self.generate(prompt, max_tokens=64).strip()

    def summarize(self, text: str, max_words: int = 150) -> str:
        prompt = f"Summarize the following text in at most {max_words} words:\n\n{text}"
        return self.generate(prompt, max_tokens=512)

    def extract_json(self, prompt: str, schema_hint: str = "") -> str:
        full_prompt = prompt
        if schema_hint:
            full_prompt += f"\n\nRespond with valid JSON matching this schema: {schema_hint}"
        else:
            full_prompt += "\n\nRespond with valid JSON only — no markdown, no explanation."
        return self.generate(full_prompt, max_tokens=2048)

    def chat(self, messages: list[dict], system: str = "") -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": config.MAX_TOKENS,
            "messages": messages,
            "thinking": {"type": "adaptive"},
        }
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        response = self.client.messages.create(**kwargs)
        return next((b.text for b in response.content if b.type == "text"), "")
