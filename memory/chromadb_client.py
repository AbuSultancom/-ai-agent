import logging
import os
import uuid

logger = logging.getLogger(__name__)


class ChromaDBClient:
    """Persistent vector store using ChromaDB."""

    COLLECTION_NAME = "agent_memory"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._client = None
        self._collection = None

    @property
    def client(self):
        if self._client is None:
            import chromadb
            os.makedirs(self.db_path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.db_path)
            logger.info("ChromaDB connected at %s", self.db_path)
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def store_memory(self, key: str, content: str, metadata: dict | None = None) -> None:
        meta = {"key": key, **(metadata or {})}
        # Upsert by key — use key as document id (sanitized)
        doc_id = key.replace(" ", "_")[:512]
        existing = self.collection.get(ids=[doc_id])
        if existing["ids"]:
            self.collection.update(ids=[doc_id], documents=[content], metadatas=[meta])
        else:
            self.collection.add(ids=[doc_id], documents=[content], metadatas=[meta])
        logger.debug("Stored memory: %s", key)

    def retrieve_memory(self, key: str) -> str | None:
        doc_id = key.replace(" ", "_")[:512]
        result = self.collection.get(ids=[doc_id])
        if result["documents"]:
            return result["documents"][0]
        return None

    def search_memory(self, query: str, n_results: int = 5) -> list[dict]:
        count = self.collection.count()
        if count == 0:
            return []
        n = min(n_results, count)
        results = self.collection.query(query_texts=[query], n_results=n)
        output = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            dist = results["distances"][0][i] if results.get("distances") else None
            output.append(
                {
                    "key": meta.get("key", results["ids"][0][i]),
                    "content": doc,
                    "metadata": meta,
                    "score": round(1 - dist, 4) if dist is not None else None,
                }
            )
        return output

    def delete_memory(self, key: str) -> bool:
        doc_id = key.replace(" ", "_")[:512]
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception as exc:
            logger.warning("Delete failed for key %s: %s", key, exc)
            return False

    def list_memories(self, limit: int = 100) -> list[dict]:
        result = self.collection.get(limit=limit)
        output = []
        for i, doc in enumerate(result["documents"]):
            meta = result["metadatas"][i] if result.get("metadatas") else {}
            output.append({"key": meta.get("key", result["ids"][i]), "content": doc[:200]})
        return output

    def count(self) -> int:
        return self.collection.count()
