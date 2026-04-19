# AI Agent — CLAUDE.md

## Architecture

Python/Flask AI agent powered by Claude Opus 4.7 with an agentic tool-use loop.

### Key components

| Path | Role |
|---|---|
| `core/config.py` | Environment config (all settings via `.env`) |
| `core/app.py` | Flask REST API (`/api/task`, `/api/memory`, `/health`) |
| `core/orchestrator.py` | `AIOrchestrator` — Claude agentic loop with 7 tools |
| `agents/planner_agent.py` | `PlannerAgent` — Claude-based task decomposition |
| `agents/executor_agent.py` | `ExecutorAgent` — step-by-step tool dispatch |
| `agents/memory_agent.py` | `MemoryAgent` — store/recall/summarize sessions |
| `tools/llm_tools.py` | `LLMTools` — generate, stream, classify, summarize |
| `tools/os_tools.py` | `OSTools` — safe bash execution with blocklist |
| `tools/web_tools.py` | `WebTools` — HTTP fetch + BeautifulSoup extraction |
| `tools/file_tools.py` | `FileTools` — read, write, search, list files |
| `memory/chromadb_client.py` | `ChromaDBClient` — persistent vector store |
| `memory/memory_manager.py` | `MemoryManager` — high-level memory interface |
| `orchestrator.py` | CLI entry point: `serve`, `run`, `plan` |

## Running

```bash
# Install deps
pip install -r requirements.txt

# Copy and fill env
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env

# Start API server
python orchestrator.py serve

# Run a task directly from CLI
python orchestrator.py run "Write a Python script that counts words in a file"

# Show task plan only
python orchestrator.py plan "Build a REST API for a todo list"
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/task` | Submit async task → returns `task_id` |
| GET | `/api/task/<id>` | Poll task status and output |
| GET | `/api/task/<id>/stream` | SSE stream of task output |
| POST | `/api/task/run` | Synchronous task execution |
| GET | `/api/tasks` | List recent tasks |
| POST | `/api/memory` | Store a memory |
| POST | `/api/memory/search` | Semantic memory search |

## Tools available to the agent

- `execute_bash` — run shell commands with timeout and safety blocklist
- `read_file` — read file contents
- `write_file` — write/append to files
- `search_files` — glob pattern file search
- `web_fetch` — HTTP fetch with text/links/html extraction
- `memory_store` — persist info in ChromaDB
- `memory_search` — semantic search over stored memories

## Docker

```bash
docker compose up --build
```

## Dev notes

- Model: `claude-opus-4-7` with `thinking: {type: "adaptive"}` and prompt caching on system prompt
- ChromaDB persists at `./data/chromadb` (or `CHROMADB_PATH`)
- Safety: bash commands are checked against a blocklist before execution
- Web: uses `requests` + `BeautifulSoup`; Playwright available for screenshots
