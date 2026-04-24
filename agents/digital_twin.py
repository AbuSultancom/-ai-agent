"""
Digital Twin Agent — builds a persistent model of the user's thinking style,
coding patterns, and knowledge domains. Answers questions as the user would.

Architecture:
  Ingestion layer  → reads code files, documents, chat history
  Profile builder  → extracts style, patterns, preferences with Claude
  Memory layer     → stores everything in ChromaDB (semantic retrieval)
  Twin responder   → answers questions using the user's mental model
  Probing engine   → asks questions to deepen understanding of the user
"""

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Iterator

import anthropic

from core.config import config

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# ── System prompts ──────────────────────────────────────────────────────────

_PROFILER_SYSTEM = """You are an expert at analyzing a person's thinking style, coding patterns,
and intellectual personality from their work.

Analyze the provided content and extract a structured profile containing:
- coding_style: language preferences, naming conventions, architectural choices, complexity tolerance
- problem_approach: how they decompose problems, preferred abstractions, debugging style
- knowledge_domains: their areas of expertise and depth
- learning_style: how they absorb and apply new concepts
- communication_style: how they explain things, level of detail, preferred analogies
- personality_traits: intellectual traits visible in their work (systematic, creative, pragmatic, etc.)

Respond ONLY with a JSON object. No extra text."""

_PROBING_SYSTEM = """You are a thoughtful intellectual companion who is trying to deeply understand
a person's thinking patterns and mental models.

Based on what you know about the user so far, generate ONE insightful probing question that will
reveal something important about how they think, approach problems, or make decisions.

The question should be:
- Specific enough to reveal thinking patterns (not generic)
- Related to their known interests or work
- Open-ended, requiring more than yes/no

Respond with ONLY the question text."""

_TWIN_SYSTEM_TEMPLATE = """You are the Digital Twin of {name}.

You have deeply analyzed {name}'s:
- Coding style and architectural preferences
- Problem-solving approach and thinking patterns
- Knowledge domains and expertise areas
- Communication style and intellectual personality

USER PROFILE:
{profile}

RELEVANT MEMORIES:
{memories}

When answering questions, respond exactly as {name} would:
- Use their characteristic reasoning style
- Draw on their specific knowledge domains
- Apply their preferred solution approaches
- Match their communication style and level of detail
- Reference their past patterns and preferences when relevant

You are NOT a general AI assistant — you are a precise reflection of {name}'s mind."""


class DigitalTwin:
    """Builds and maintains a digital twin of the user."""

    def __init__(self, user_name: str = "the user", chromadb_path: str = ""):
        self._name = user_name
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._profile: dict = {}
        self._lock = threading.Lock()
        self._ingestion_log: list[dict] = []

        # Vector memory for twin
        chroma_path = chromadb_path or config.CHROMADB_PATH
        self._collection_name = "digital_twin"
        self._init_memory(chroma_path)

    def _init_memory(self, path: str):
        try:
            import chromadb
            self._chroma = chromadb.PersistentClient(path=path)
            self._collection = self._chroma.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            # Load stored profile if it exists
            stored = self._collection.get(ids=["__profile__"])
            if stored["documents"]:
                try:
                    self._profile = json.loads(stored["documents"][0])
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Twin memory init failed: %s", e)
            self._collection = None

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_code(self, code: str, filename: str = "", language: str = "python") -> dict:
        """Analyze a code file and update the user profile."""
        prompt = (
            f"File: {filename or 'unknown'} ({language})\n\n"
            f"```{language}\n{code[:8000]}\n```\n\n"
            "Analyze this code sample and extract the author's profile."
        )
        return self._extract_and_merge_profile(prompt, source=filename or "code")

    def ingest_text(self, text: str, source: str = "") -> dict:
        """Ingest a document (notes, research, messages) and update the profile."""
        prompt = f"Source: {source}\n\nContent:\n{text[:8000]}\n\nAnalyze this content to understand the author's thinking style."
        return self._extract_and_merge_profile(prompt, source=source or "text")

    def ingest_directory(self, path: str, extensions: tuple = (".py", ".md", ".txt")) -> dict:
        """Recursively ingest all matching files from a directory."""
        p = Path(path)
        if not p.exists():
            return {"error": f"Path not found: {path}"}

        results = []
        for f in p.rglob("*"):
            if f.suffix in extensions and f.is_file():
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if len(content) < 50:
                        continue
                    lang = {"py": "python", "md": "markdown", "txt": "text"}.get(f.suffix.lstrip("."), "text")
                    result = self.ingest_code(content, filename=str(f.relative_to(p)), language=lang)
                    results.append({"file": str(f.name), "ok": "error" not in result})
                except Exception as e:
                    results.append({"file": str(f.name), "error": str(e)})

        return {"ingested": len(results), "files": results}

    def _extract_and_merge_profile(self, prompt: str, source: str) -> dict:
        try:
            resp = self._client.messages.create(
                model=config.MODEL,
                max_tokens=2000,
                system=_PROFILER_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            start, end = text.find("{"), text.rfind("}") + 1
            new_profile = json.loads(text[start:end]) if start >= 0 else {}

            with self._lock:
                self._merge_profile(new_profile)
                self._save_profile()
                self._store_memory(source, prompt[:500], {"type": "ingestion", "source": source})

            log_entry = {"source": source, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "fields": list(new_profile.keys())}
            self._ingestion_log.append(log_entry)
            return {"ok": True, "profile_keys": list(new_profile.keys()), "source": source}
        except Exception as e:
            logger.error("Ingestion failed: %s", e)
            return {"error": str(e), "source": source}

    def _merge_profile(self, new: dict):
        """Deep merge new profile data into existing profile."""
        for key, val in new.items():
            if key not in self._profile:
                self._profile[key] = val
            elif isinstance(val, list) and isinstance(self._profile[key], list):
                # Deduplicate list merge
                existing = set(str(x) for x in self._profile[key])
                self._profile[key].extend(x for x in val if str(x) not in existing)
            elif isinstance(val, dict) and isinstance(self._profile[key], dict):
                self._profile[key].update(val)
            else:
                # Keep latest observation
                self._profile[key] = val

    def _save_profile(self):
        if self._collection is None:
            return
        try:
            doc = json.dumps(self._profile, ensure_ascii=False)
            self._collection.upsert(ids=["__profile__"], documents=[doc],
                                    metadatas=[{"type": "profile"}])
        except Exception as e:
            logger.warning("Profile save failed: %s", e)

    def _store_memory(self, key: str, content: str, metadata: dict):
        if self._collection is None:
            return
        try:
            mid = f"mem_{hash(key + content) % 10**9}"
            self._collection.upsert(ids=[mid], documents=[content], metadatas=[metadata])
        except Exception as e:
            logger.warning("Memory store failed: %s", e)

    def _recall_memories(self, query: str, n: int = 5) -> str:
        if self._collection is None:
            return ""
        try:
            results = self._collection.query(query_texts=[query], n_results=n,
                                              where={"type": "ingestion"})
            docs = results.get("documents", [[]])[0]
            return "\n---\n".join(docs[:n])
        except Exception:
            return ""

    # ── Twin Response ─────────────────────────────────────────────────────────

    def respond(self, question: str, stream: bool = False) -> str | Iterator[str]:
        """Answer a question as the digital twin of the user."""
        memories = self._recall_memories(question)
        profile_text = json.dumps(self._profile, indent=2, ensure_ascii=False) if self._profile else "Profile not yet built."
        system = _TWIN_SYSTEM_TEMPLATE.format(
            name=self._name,
            profile=profile_text[:4000],
            memories=memories[:2000],
        )

        if stream:
            return self._stream_response(question, system)

        resp = self._client.messages.create(
            model=config.MODEL,
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": question}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def _stream_response(self, question: str, system: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=config.MODEL,
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": question}],
        ) as stream:
            for text in stream.text_stream:
                yield text

    # ── Probing Engine ────────────────────────────────────────────────────────

    def generate_probing_question(self) -> str:
        """Generate a question designed to reveal the user's thinking patterns."""
        profile_summary = json.dumps(self._profile, ensure_ascii=False)[:3000] if self._profile else "No profile yet."
        resp = self._client.messages.create(
            model=config.MODEL,
            max_tokens=200,
            system=_PROBING_SYSTEM,
            messages=[{"role": "user", "content": f"What I know about the user so far:\n{profile_summary}"}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def record_answer(self, question: str, answer: str):
        """Store a probing Q&A pair to deepen the profile."""
        content = f"Q: {question}\nA: {answer}"
        self._store_memory(f"probing_{hash(question)}", content, {"type": "probing"})
        # Also update profile from the answer
        self.ingest_text(answer, source=f"probing_answer")

    # ── Introspection ─────────────────────────────────────────────────────────

    def get_profile(self) -> dict:
        with self._lock:
            return dict(self._profile)

    def get_summary(self) -> str:
        """Return a natural language summary of the user profile."""
        if not self._profile:
            return "Profile not built yet. Ingest some of your code or documents to start."
        resp = self._client.messages.create(
            model=config.MODEL,
            max_tokens=500,
            system="Summarize the provided user profile in 3-4 sentences. Be specific and insightful.",
            messages=[{"role": "user", "content": json.dumps(self._profile, ensure_ascii=False)}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def get_ingestion_log(self) -> list[dict]:
        return list(reversed(self._ingestion_log[-50:]))

    def update_name(self, name: str):
        with self._lock:
            self._name = name


# ── Singleton ──────────────────────────────────────────────────────────────────

_twin: DigitalTwin | None = None
_twin_lock = threading.Lock()


def get_twin(user_name: str = "the user") -> DigitalTwin:
    global _twin
    with _twin_lock:
        if _twin is None:
            _twin = DigitalTwin(user_name=user_name)
        return _twin
