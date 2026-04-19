"""RAG (Retrieval-Augmented Generation) — upload docs, ask questions."""

import io
import logging
import os
import re
import uuid
from collections import defaultdict

import anthropic
import chromadb

from core.config import config

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800       # characters per chunk
CHUNK_OVERLAP = 150
RAG_COLLECTION = "rag_documents"
MAX_CONTEXT_CHUNKS = 6


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end].strip())
        start += size - overlap
    return [c for c in chunks if len(c) > 50]


def _extract_text(file) -> str:
    name = file.filename.lower()
    raw = file.read()

    if name.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        except ImportError:
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(raw))
                return "\n\n".join(p.extract_text() or "" for p in reader.pages)
            except ImportError:
                return raw.decode("utf-8", errors="replace")

    # Plain text / code / markdown / CSV / JSON
    return raw.decode("utf-8", errors="replace")


class RAGEngine:
    def __init__(self, db_path: str):
        os.makedirs(db_path, exist_ok=True)
        self._client = chromadb.PersistentClient(path=db_path)
        self._collection = self._client.get_or_create_collection(
            name=RAG_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self._llm = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def ingest_file(self, file) -> dict:
        name = os.path.basename(file.filename)
        text = _extract_text(file)

        if not text.strip():
            return {"error": "Could not extract text from file", "name": name}

        # Remove existing chunks for this doc
        self.delete_document(name)

        chunks = _chunk_text(text)
        ids = [f"{name}::{i}::{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        metas = [{"doc_name": name, "chunk_index": i} for i in range(len(chunks))]

        # Batch insert (ChromaDB max 5461 per batch)
        batch = 500
        for start in range(0, len(chunks), batch):
            self._collection.add(
                ids=ids[start:start + batch],
                documents=chunks[start:start + batch],
                metadatas=metas[start:start + batch],
            )

        logger.info("Ingested %s → %d chunks", name, len(chunks))
        return {"message": f"✅ تم رفع {name} ({len(chunks)} قطعة)", "name": name, "chunks": len(chunks)}

    def query(self, question: str, n_chunks: int = MAX_CONTEXT_CHUNKS) -> str:
        count = self._collection.count()
        if count == 0:
            return "لا توجد مستندات مرفوعة بعد. ارفع ملفاً أولاً."

        n = min(n_chunks, count)
        results = self._collection.query(query_texts=[question], n_results=n)
        docs = results["documents"][0] if results.get("documents") else []
        metas = results["metadatas"][0] if results.get("metadatas") else []

        if not docs:
            return "لم يتم العثور على معلومات ذات صلة في المستندات."

        context_parts = []
        for doc, meta in zip(docs, metas):
            source = meta.get("doc_name", "?")
            context_parts.append(f"[المصدر: {source}]\n{doc}")
        context = "\n\n---\n\n".join(context_parts)

        prompt = f"""استناداً إلى المقتطفات التالية من المستندات، أجب على السؤال بدقة.
إذا لم تجد الإجابة في المقتطفات، قل ذلك بصراحة.

المقتطفات:
{context}

السؤال: {question}

الإجابة:"""

        response = self._llm.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": "You are a precise document Q&A assistant.", "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return next((b.text for b in response.content if b.type == "text"), "لا إجابة")

    def list_documents(self) -> list[dict]:
        if self._collection.count() == 0:
            return []
        result = self._collection.get(limit=10000)
        counts: dict[str, int] = defaultdict(int)
        for meta in (result.get("metadatas") or []):
            if meta:
                counts[meta.get("doc_name", "unknown")] += 1
        return [{"name": name, "chunks": cnt} for name, cnt in counts.items()]

    def delete_document(self, name: str) -> None:
        try:
            existing = self._collection.get(where={"doc_name": name})
            if existing.get("ids"):
                self._collection.delete(ids=existing["ids"])
                logger.info("Deleted document: %s (%d chunks)", name, len(existing["ids"]))
        except Exception as exc:
            logger.warning("Delete doc failed: %s", exc)
