import json
import logging
from collections.abc import Generator

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
        {
            "name": "send_email",
            "description": "Send an email notification. Requires SMTP config in environment.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                },
                "required": ["to", "subject", "body"],
            },
        },
        {
            "name": "github",
            "description": "Interact with GitHub: read repos/files/issues/PRs, create issues, search code.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_repo", "list_repos", "get_file", "list_files",
                                 "list_issues", "create_issue", "comment_on_issue",
                                 "list_prs", "create_pr", "search_code"],
                        "description": "GitHub action to perform",
                    },
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "path": {"type": "string", "description": "File path in repo"},
                    "title": {"type": "string", "description": "Issue/PR title"},
                    "body": {"type": "string", "description": "Issue/PR body"},
                    "head": {"type": "string", "description": "PR head branch"},
                    "base": {"type": "string", "description": "PR base branch"},
                    "number": {"type": "integer", "description": "Issue/PR number"},
                    "query": {"type": "string", "description": "Search query"},
                    "username": {"type": "string", "description": "GitHub username"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                    "comment": {"type": "string", "description": "Comment text"},
                },
                "required": ["action"],
            },
        },
        {
            "name": "execute_python",
            "description": "Execute Python code in a safe sandbox and return stdout/stderr. Great for calculations, data processing, generating charts, etc.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 15)",
                        "default": 15,
                    },
                },
                "required": ["code"],
            },
        },
    ]


class AIOrchestrator:
    def __init__(self):
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
            if name == "send_email":
                from core.notifications import send_email
                return send_email(inputs["to"], inputs["subject"], inputs["body"])
            if name == "github":
                from tools.github_tools import GitHubTools
                gh = GitHubTools()
                action = inputs.pop("action")
                return gh.dispatch(action, **inputs)
            if name == "execute_python":
                from tools.code_sandbox import CodeSandbox
                sandbox = CodeSandbox()
                result = sandbox.execute(inputs["code"], inputs.get("timeout", 15))
                return sandbox.format_result(result)
            return f"Unknown tool: {name}"
        except Exception as exc:
            logger.warning("Tool %s raised: %s", name, exc)
            return f"Error in {name}: {exc}"

    def run_task(self, task: str) -> Generator[str, None, None]:
        """Run a task and yield text chunks as they become available."""
        from core import model_router
        messages: list[dict] = [{"role": "user", "content": task}]
        model = config.MODEL

        for iteration in range(config.MAX_AGENT_ITERATIONS):
            response = model_router.chat_with_tools(
                messages,
                self.tools,
                model=model,
                system=SYSTEM_PROMPT,
            )

            if response["text"]:
                yield response["text"]

            if response["stop_reason"] == "end_turn":
                break

            if response["stop_reason"] != "tool_use":
                logger.warning("Unexpected stop_reason: %s", response["stop_reason"])
                break

            # Add assistant turn to history
            messages.append(response["_history_assistant"])

            # Execute tool calls
            tool_results = []
            for tc in response["tool_calls"]:
                preview = json.dumps(tc["inputs"], ensure_ascii=False)[:120]
                yield f"\n\n**[{tc['name']}]** `{preview}`\n"
                result = self._dispatch_tool(tc["name"], tc["inputs"])
                tool_results.append({"id": tc["id"], "result": result})

            # Add tool results in the right backend format
            messages.extend(model_router.build_tool_result_messages(tool_results, model))

            if iteration == config.MAX_AGENT_ITERATIONS - 1:
                yield "\n\n[Max iterations reached]"

    def run_task_sync(self, task: str) -> str:
        return "".join(self.run_task(task))
