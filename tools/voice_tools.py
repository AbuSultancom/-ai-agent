"""Voice tools — Whisper STT transcription, optional TTS output."""

import logging
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Lazy-loaded Whisper model (avoids ~1s import cost at startup)
_whisper_model = None
_whisper_model_size = "base"   # tiny | base | small | medium | large


def _get_model(size: str = _whisper_model_size):
    global _whisper_model, _whisper_model_size
    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "openai-whisper not installed. Run: pip install openai-whisper"
        )
    if _whisper_model is None or size != _whisper_model_size:
        logger.info("Loading Whisper model '%s'…", size)
        _whisper_model = whisper.load_model(size)
        _whisper_model_size = size
    return _whisper_model


def transcribe_file(
    audio_path: str,
    language: str | None = None,
    model_size: str = "base",
) -> dict:
    """
    Transcribe an audio file using Whisper.

    Args:
        audio_path: Path to audio file (wav, mp3, m4a, ogg, webm, …)
        language: ISO code e.g. "en", "ar" — None = auto-detect
        model_size: Whisper model size (tiny/base/small/medium/large)

    Returns:
        {"text": str, "language": str, "duration_s": float, "segments": list}
    """
    model = _get_model(model_size)
    options = {}
    if language:
        options["language"] = language

    result = model.transcribe(audio_path, **options)
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", "unknown"),
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.get("segments", [])
        ],
    }


def transcribe_bytes(
    audio_bytes: bytes,
    ext: str = ".wav",
    language: str | None = None,
    model_size: str = "base",
) -> dict:
    """Transcribe raw audio bytes (saves to temp file, then runs Whisper)."""
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return transcribe_file(tmp_path, language=language, model_size=model_size)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def speak(text: str, rate: int = 175) -> bool:
    """
    Text-to-speech using espeak (if available) or pyttsx3.
    Returns True if speech was produced.
    """
    import shutil
    import subprocess

    if shutil.which("espeak-ng") or shutil.which("espeak"):
        binary = shutil.which("espeak-ng") or "espeak"
        try:
            subprocess.run([binary, f"-s{rate}", text], check=True, capture_output=True)
            return True
        except Exception as e:
            logger.warning("espeak error: %s", e)

    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as e:
        logger.warning("pyttsx3 error: %s", e)

    return False


def whisper_available() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def get_available_models() -> list[str]:
    return ["tiny", "base", "small", "medium", "large"]
