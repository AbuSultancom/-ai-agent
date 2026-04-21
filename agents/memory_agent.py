import logging

from core.config import config

logger = logging.getLogger(__name__)


class MemoryAgent:
    """Manages agent memory: store context, search past knowledge, summarize sessions."""

    def __init__(self):
        from memory.memory_manager import MemoryManager
        self.memory = MemoryManager(config.CHROMADB_PATH)

    def remember(self, key: str, content: str, metadata: dict | None = None) -> str:
        self.memory.store(key, content, metadata or {})
        return f"Remembered: {key}"

    def recall(self, query: str, n: int = 5) -> list[dict]:
        return self.memory.search(query, n)

    def recall_formatted(self, query: str, n: int = 5) -> str:
        results = self.recall(query, n)
        if not results:
            return "No relevant memories found."
        lines = [f"**Memories for:** _{query}_\n"]
        for r in results:
            lines.append(f"- **{r.get('key', '?')}**: {r.get('content', '')[:200]}")
        return "\n".join(lines)

    def summarize_and_store(self, session_id: str, conversation: list[dict]) -> str:
        """Summarize a conversation and store it in memory."""
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        convo_text = "\n".join(
            f"{m['role'].upper()}: {m.get('content', '')}"
            for m in conversation
            if isinstance(m.get("content"), str)
        )

        response = client.messages.create(
            model=config.MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"Summarize this conversation in 3-5 bullet points:\n\n{convo_text[:8000]}",
                }
            ],
        )
        summary = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        key = f"session:{session_id}"
        self.memory.store(key, summary, {"session_id": session_id, "type": "summary"})
        return summary
