import json
import logging
from collections.abc import Generator

import anthropic

from core.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a powerful AI agent capable of completing complex tasks autonomously.

You have access to these tools:
- **execute_bash**: Run bash commands (files, packages, scripts, system ops)
- **read_file**: Read any file's contents
- **write_file**: Write or append content to files
- **search_files**: Find files matching a glob pattern
- **web_fetch**: Fetch and extract content from a URL
- **memory_store**: Persist information for future sessions
- **memory_search**: Semantic search over stored memories

How to approach tasks:
1. Break complex tasks into concrete steps
2. Use tools proactively — gather info before acting
3. Verify results after each important step
4. Store key findings in memory for reuse
5. Report progress clearly with what you did and what you found

Safety rules: never delete system files, never expose secrets, confirm before irreversible operations."""


def _build_tool_definitions() -> list[dict]:
    return [
        {
            "name": "execute_bash",
            "description": "Execute a bash command and return stdout/stderr. Use for filesystem ops, running scripts, installing packages, checking system info.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        },
        {
            "name": "read_file",
            "description": "Read the contents of a file from disk.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"}
                },
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Write or append content to a file. Creates parent directories automatically.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "Content to write"},
                    "mode": {
                        "type": "string",
                        "enum": ["w", "a"],
                        "description": "w=overwrite (default), a=append",
                        "default": "w",
                    },
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "search_files",
            "description": "Search for files matching a glob pattern in a directory.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py'",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search (default: current)",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "web_fetch",
            "description": "Fetch a URL and return its text content. Good for documentation, APIs, web scraping.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "extract": {
                        "type": "string",
                        "enum": ["text", "links", "html"],
                        "description": "What to extract: text (default), links, or raw html",
                        "default": "text",
                    },
                },
                "required": ["url"],
            },
        },
        {
            "name": "memory_store",
            "description": "Store a piece of information persistently so it can be recalled later via memory_search.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Unique identifier for this memory",
                    },
                    "content": {"type": "string", "description": "Information to remember"},
                    "metadata": {
                        "type": "object",
                        "description": "Optional tags or labels",
                    },
                },
                "required": ["key", "content"],
            },
        },
        {
            "name": "memory_search",
            "description": "Search stored memories using semantic similarity.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "n_results": {
                        "type": "integer",
                        "description": "How many results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    ]


class AIOrchestrator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.tools = _build_tool_definitions()
        self._os_tools = None
        self._web_tools = None
        self._file_tools = None
        self._memory = None

    # Lazy-load tools to avoid circular imports and heavy init at startup
    @property
    def os_tools(self):
        if self._os_tools is None:
            from tools.os_tools import OSTools
            self._os_tools = OSTools()
        return self._os_tools

    @property
    def web_tools(self):
        if self._web_tools is None:
            from tools.web_tools import WebTools
            self._web_tools = WebTools()
        return self._web_tools

    @property
    def file_tools(self):
        if self._file_tools is None:
            from tools.file_tools import FileTools
            self._file_tools = FileTools()
        return self._file_tools

    @property
    def memory(self):
        if self._memory is None:
            from memory.memory_manager import MemoryManager
            self._memory = MemoryManager(config.CHROMADB_PATH)
        return self._memory

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        try:
            if name == "execute_bash":
                return self.os_tools.execute_bash(
                    inputs["command"], inputs.get("timeout", config.BASH_TIMEOUT)
                )
            if name == "read_file":
                return self.file_tools.read_file(inputs["path"])
            if name == "write_file":
                return self.file_tools.write_file(
                    inputs["path"], inputs["content"], inputs.get("mode", "w")
                )
            if name == "search_files":
                return self.file_tools.search_files(
                    inputs["pattern"], inputs.get("directory", ".")
                )
            if name == "web_fetch":
                return self.web_tools.fetch(inputs["url"], inputs.get("extract", "text"))
            if name == "memory_store":
                self.memory.store(
                    inputs["key"], inputs["content"], inputs.get("metadata", {})
                )
                return f"Stored: {inputs['key']}"
            if name == "memory_search":
                results = self.memory.search(inputs["query"], inputs.get("n_results", 5))
                return json.dumps(results, ensure_ascii=False, indent=2)
            return f"Unknown tool: {name}"
        except Exception as exc:
            logger.warning("Tool %s raised: %s", name, exc)
            return f"Error in {name}: {exc}"

    def run_task(self, task: str) -> Generator[str, None, None]:
        """Run a task and yield text chunks as they become available."""
        messages: list[dict] = [{"role": "user", "content": task}]
        system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        for iteration in range(config.MAX_AGENT_ITERATIONS):
            with self.client.messages.stream(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                tools=self.tools,
                messages=messages,
            ) as stream:
                response = stream.get_final_message()

            # Yield text blocks to caller
            for block in response.content:
                if block.type == "text" and block.text:
                    yield block.text

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                break

            # Execute all tool calls in this turn
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    preview = json.dumps(block.input, ensure_ascii=False)[:120]
                    yield f"\n\n**[{block.name}]** `{preview}`\n"
                    result = self._dispatch_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

            if iteration == config.MAX_AGENT_ITERATIONS - 1:
                yield "\n\n[Max iterations reached]"

    def run_task_sync(self, task: str) -> str:
        return "".join(self.run_task(task))
