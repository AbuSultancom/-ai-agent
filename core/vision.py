"""Vision — analyze images using Claude's multimodal capabilities."""

import base64
import io
import logging
import os

import anthropic

from core import model_router
from core.config import config

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_VISION_SYSTEM = """You are an expert image analyst. Describe and analyze images thoroughly.
Identify objects, text, people, scenes, colors, patterns, and any other relevant details.
If asked a specific question, answer it directly based on what you see in the image.
Respond in the same language as the question."""


class VisionEngine:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._is_claude = model_router.is_claude(config.MODEL)

    def _local_model_unsupported(self) -> str:
        return f"Vision requires a Claude model. Current model '{config.MODEL}' does not support image input. Set MODEL=claude-opus-4-7 (or any claude-*) in .env."

    def _encode_image(self, data: bytes, mime_type: str) -> dict:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.standard_b64encode(data).decode(),
            },
        }

    def analyze(self, image_data: bytes, mime_type: str, question: str = "") -> str:
        if mime_type not in SUPPORTED_TYPES:
            return f"Unsupported image type: {mime_type}. Use JPEG, PNG, GIF, or WebP."
        if not self._is_claude:
            return self._local_model_unsupported()

        prompt = question or "Describe this image in detail. What do you see?"

        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": _VISION_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": [
                    self._encode_image(image_data, mime_type),
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    def analyze_from_file(self, file) -> tuple[str, str]:
        """Returns (analysis, mime_type)."""
        data = file.read()
        mime_type = file.content_type or "image/jpeg"
        return self.analyze(data, mime_type), mime_type

    def analyze_from_url(self, url: str, question: str = "") -> str:
        import requests
        r = requests.get(url, timeout=config.WEB_TIMEOUT)
        r.raise_for_status()
        mime_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        return self.analyze(r.content, mime_type, question)

    def compare_images(self, img1: bytes, mime1: str, img2: bytes, mime2: str) -> str:
        if not self._is_claude:
            return self._local_model_unsupported()
        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    self._encode_image(img1, mime1),
                    self._encode_image(img2, mime2),
                    {"type": "text",
                     "text": "Compare these two images in detail. What are the similarities and differences?"},
                ],
            }],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    def extract_text_ocr(self, image_data: bytes, mime_type: str) -> str:
        if not self._is_claude:
            return self._local_model_unsupported()
        response = self.client.messages.create(
            model=config.MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    self._encode_image(image_data, mime_type),
                    {"type": "text",
                     "text": "Extract ALL text from this image exactly as it appears. "
                             "Preserve formatting where possible. Output only the extracted text."},
                ],
            }],
        )
        return next((b.text for b in response.content if b.type == "text"), "")
