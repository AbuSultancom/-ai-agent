import logging

from memory.chromadb_client import ChromaDBClient

logger = logging.getLogger(__name__)


class MemoryManager:
    """High-level memory interface used by the orchestrator and agents."""

    def __init__(self, db_path: str):
        self._client = ChromaDBClient(db_path)

    def store(self, key: str, content: str, metadata: dict | None = None) -> None:
        self._client.store_memory(key, content, metadata)

    def retrieve(self, key: str) -> str | None:
        return self._client.retrieve_memory(key)

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        return self._client.search_memory(query, n_results)

    def delete(self, key: str) -> bool:
        return self._client.delete_memory(key)

    def list_all(self, limit: int = 50) -> list[dict]:
        return self._client.list_memories(limit)

    def count(self) -> int:
        return self._client.count()

    def store_conversation_turn(
        self, session_id: str, turn_index: int, role: str, content: str
    ) -> None:
        key = f"conv:{session_id}:{turn_index}:{role}"
        self.store(key, content, {"session_id": session_id, "role": role, "turn": turn_index})

    def get_relevant_context(self, query: str, n: int = 3) -> str:
        results = self.search(query, n)
        if not results:
            return ""
        lines = []
        for r in results:
            lines.append(f"[Memory: {r['key']}]\n{r['content'][:400]}")
        return "\n\n".join(lines)
