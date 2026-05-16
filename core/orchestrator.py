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
- **web_fetch**: Fetch and extract content from a URL (fast, text-only)
- **browser_screenshot**: Open a URL in a real browser and take a screenshot — use when you need to SEE a page visually
- **browser_get_text**: Open a URL in a real browser and extract all visible text (handles JS-rendered pages)
- **browser_click**: Navigate to a URL, click an element by CSS selector, return updated text
- **browser_fill_form**: Navigate to a URL, fill form fields and submit — returns final URL + screenshot
- **memory_store**: Persist information for future sessions
- **memory_search**: Semantic search over stored memories
- **web_search**: Search the web in real-time via DuckDuckGo — use for current events, facts, news
- **git**: Git operations (status/diff/log/commit/push/pull) — use when user asks about code changes
- **doc_search**: Search over uploaded documents using semantic similarity

When the user says "open X", "browse to X", "show me X website", "take a screenshot of X", or similar — always use browser_screenshot.
When extracting content from a JS-heavy page, prefer browser_get_text over web_fetch.

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
        {
            "name": "web_search",
            "description": "Search the web via DuckDuckGo and return top results with titles, URLs, and snippets. Use for current events, facts, or anything needing real-time information.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Number of results (default 8)", "default": 8},
                    "news": {"type": "boolean", "description": "Search news instead of web (default false)", "default": False},
                },
                "required": ["query"],
            },
        },
        {
            "name": "git",
            "description": "Run git operations: status, diff, log, add, commit, push, pull, branches.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "diff", "log", "add", "commit", "push", "pull", "branches"],
                        "description": "Git operation to perform",
                    },
                    "path": {"type": "string", "description": "File path for diff/add"},
                    "message": {"type": "string", "description": "Commit message"},
                    "n": {"type": "integer", "description": "Number of log entries", "default": 10},
                    "branch": {"type": "string", "description": "Branch name for push"},
                },
                "required": ["action"],
            },
        },
        {
            "name": "doc_search",
            "description": "Search over uploaded documents using semantic similarity. Use when the user uploads a file and asks questions about it.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Question or search query"},
                    "n_results": {"type": "integer", "description": "Number of chunks to return (default 4)", "default": 4},
                },
                "required": ["query"],
            },
        },
        {
            "name": "browser_screenshot",
            "description": "Open a URL in a real Chromium browser and take a screenshot. Use when the user asks to open/browse/show a website, or when you need to visually inspect a page. Returns a screenshot URL.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to (include https://)"},
                    "full_page": {"type": "boolean", "description": "Capture full scrollable page (default true)", "default": True},
                },
                "required": ["url"],
            },
        },
        {
            "name": "browser_get_text",
            "description": "Open a URL in a real browser and extract all visible text. Handles JavaScript-rendered pages that web_fetch cannot read.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "browser_click",
            "description": "Navigate to a URL, click an element matching a CSS selector, and return the updated page text.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to"},
                    "selector": {"type": "string", "description": "CSS selector of the element to click"},
                },
                "required": ["url", "selector"],
            },
        },
        {
            "name": "browser_fill_form",
            "description": "Navigate to a URL, fill form fields by CSS selector, optionally submit, and return the result with a screenshot.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to"},
                    "fields": {
                        "type": "object",
                        "description": "Map of CSS selector → value to type, e.g. {\"#search\": \"python\"}"
                    },
                    "submit_selector": {"type": "string", "description": "CSS selector to click for submission (optional)", "default": ""},
                },
                "required": ["url", "fields"],
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
        self._browser_tools = None

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

    @property
    def browser_tools(self):
        if self._browser_tools is None:
            from tools.browser_tools import BrowserTools
            self._browser_tools = BrowserTools()
        return self._browser_tools

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
            if name == "web_search":
                from tools.search_tools import SearchTools
                st = SearchTools()
                if inputs.get("news"):
                    return st.news_search(inputs["query"], inputs.get("max_results", 6))
                return st.web_search(inputs["query"], inputs.get("max_results", 8))
            if name == "git":
                from tools.git_tools import GitTools
                gt = GitTools()
                action = inputs.pop("action", "status")
                return gt.dispatch(action, **inputs)
            if name == "doc_search":
                results = self.memory.search(inputs["query"], inputs.get("n_results", 4))
                # Filter to doc: sources only
                doc_results = [r for r in results if str(r.get("key","")).startswith("doc:")]
                return json.dumps(doc_results if doc_results else results, ensure_ascii=False, indent=2)
            if name == "browser_screenshot":
                result = self.browser_tools.screenshot(inputs["url"], inputs.get("full_page", True))
                return json.dumps({"screenshot_url": result["url"], "path": result["path"]})
            if name == "browser_get_text":
                return self.browser_tools.get_text(inputs["url"])
            if name == "browser_click":
                return self.browser_tools.click_and_get(inputs["url"], inputs["selector"])
            if name == "browser_fill_form":
                result = self.browser_tools.fill_form(
                    inputs["url"], inputs["fields"], inputs.get("submit_selector", "")
                )
                return json.dumps(result)
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
                if tc["name"] == "browser_screenshot":
                    try:
                        shot = json.loads(result)
                        yield f"\n\n**[screenshot_image]** `{shot.get('screenshot_url', '')}`\n"
                    except Exception:
                        pass

            # Add tool results in the right backend format
            messages.extend(model_router.build_tool_result_messages(tool_results, model))

            if iteration == config.MAX_AGENT_ITERATIONS - 1:
                yield "\n\n[Max iterations reached]"

    def run_task_sync(self, task: str) -> str:
        return "".join(self.run_task(task))

    def run_with_messages(self, messages: list[dict], model: str | None = None) -> Generator[str, None, None]:
        """Like run_task but accepts a pre-built message list (supports chat history)."""
        from core import model_router
        model = model or config.MODEL
        msgs = list(messages)

        for iteration in range(config.MAX_AGENT_ITERATIONS):
            response = model_router.chat_with_tools(msgs, self.tools, model=model, system=SYSTEM_PROMPT)
            if response["text"]:
                yield response["text"]
            if response["stop_reason"] == "end_turn":
                break
            if response["stop_reason"] != "tool_use":
                break
            msgs.append(response["_history_assistant"])
            tool_results = []
            for tc in response["tool_calls"]:
                preview = json.dumps(tc["inputs"], ensure_ascii=False)[:120]
                yield f"\n\n**[{tc['name']}]** `{preview}`\n"
                result = self._dispatch_tool(tc["name"], tc["inputs"])
                tool_results.append({"id": tc["id"], "result": result})
                if tc["name"] == "browser_screenshot":
                    try:
                        shot = json.loads(result)
                        yield f"\n\n**[screenshot_image]** `{shot.get('screenshot_url', '')}`\n"
                    except Exception:
                        pass
            msgs.extend(model_router.build_tool_result_messages(tool_results, model))
            if iteration == config.MAX_AGENT_ITERATIONS - 1:
                yield "\n\n[Max iterations reached]"
