# AI Agent

A production-grade autonomous AI agent powered by **Claude Opus 4.7** with an agentic tool-use loop, full web dashboard, local model support via Ollama, and OS-level system service integration.

---

## Features

| Category | Features |
|---|---|
| **Core AI** | Agentic task loop (30 iterations), extended thinking, prompt caching |
| **Local Models** | Ollama integration — run llama3.2, mistral, qwen, deepseek locally |
| **Model Routing** | Automatic Claude ↔ Ollama routing by model name prefix |
| **Chat** | Multi-turn chat with personas, per-session history, model selector |
| **Memory** | Persistent vector memory (ChromaDB), semantic search |
| **RAG** | Upload documents (PDF/TXT/MD/code), ask questions against them |
| **Vision** | Image analysis, OCR, URL-based image analysis (Claude Vision) |
| **Data Analysis** | CSV/Excel analysis with AI, chart generation (matplotlib) |
| **Personas** | 8 built-in + custom personas (Developer, Analyst, Writer, …) |
| **Templates** | Prompt templates with `{{variable}}` substitution |
| **Batch Tasks** | Parallel execution of multiple tasks (ThreadPoolExecutor) |
| **Scheduler** | Cron-based task scheduling (APScheduler) |
| **Monitoring** | Token usage, cost tracking, request logs, hourly summaries |
| **Auth** | JWT authentication (optional, HMAC-HS256) |
| **Rate Limiting** | Per-IP token-bucket rate limiting |
| **Database** | SQLite by default, PostgreSQL supported |
| **Browser** | Playwright browser automation for web tasks |
| **Code Sandbox** | Safe Python execution with import blocklist |
| **API Testing** | Built-in HTTP client for testing external APIs |
| **Notifications** | Email (SMTP), Slack, Discord webhooks |
| **Docker** | Full docker-compose setup |
| **System Service** | systemd integration — runs as a persistent OS service |

---

## Architecture

```
-ai-agent/
├── core/
│   ├── app.py              # Flask REST API (40+ endpoints)
│   ├── orchestrator.py     # Agentic Claude loop (tool-use, 30 iter)
│   ├── chat.py             # Multi-turn chat with session history
│   ├── config.py           # All settings via .env
│   ├── local_models.py     # Ollama client (list/pull/delete/chat)
│   ├── model_router.py     # Routes Claude vs Ollama by model name
│   ├── personas.py         # Built-in + custom personas
│   └── monitoring.py       # Usage and cost tracking
├── agents/
│   ├── planner_agent.py    # Task decomposition (Claude)
│   ├── executor_agent.py   # Step-by-step tool dispatch
│   └── memory_agent.py     # Memory store/recall/summarize
├── tools/
│   ├── llm_tools.py        # generate, stream, classify, summarize
│   ├── os_tools.py         # Safe bash execution with blocklist
│   ├── web_tools.py        # HTTP fetch + BeautifulSoup
│   ├── file_tools.py       # read, write, search, list
│   ├── db_tools.py         # SQL query sandbox
│   ├── vision_tools.py     # Image analysis (Claude Vision)
│   ├── data_tools.py       # CSV/Excel + chart generation
│   ├── browser_tools.py    # Playwright browser automation
│   └── code_sandbox.py     # Safe Python execution
├── memory/
│   ├── chromadb_client.py  # ChromaDB persistent vector store
│   └── memory_manager.py   # High-level memory interface
├── templates/index.html    # Web dashboard (12 tabs)
├── static/
│   ├── css/main.css
│   └── js/main.js
├── ai-agent.service        # systemd unit file
├── scripts/
│   ├── install.sh          # OS service installer
│   ├── uninstall.sh        # Service removal
│   └── ai                  # System-wide CLI wrapper
├── orchestrator.py         # CLI entry point
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/abusultancom/-ai-agent.git ai-agent
cd ai-agent
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure

Edit `.env` and set your API key:

```env
ANTHROPIC_API_KEY=sk-ant-...
MODEL=claude-opus-4-7
```

### 3. Run

```bash
# Web server + dashboard
python orchestrator.py serve
# Dashboard at http://localhost:5000

# Run a single task from CLI
python orchestrator.py run "Write a Python script that counts words in a file"

# Show task plan only (no execution)
python orchestrator.py plan "Build a REST API for a todo list"
```

---

## Install as a System Service (Linux)

Run the agent as a **persistent systemd service** that starts on boot and restarts automatically on failure.

```bash
# Install and start the service
sudo bash scripts/install.sh

# Check status
systemctl status ai-agent

# View live logs
journalctl -u ai-agent -f
```

After installation a system-wide `ai` command is available from any directory:

```bash
ai "Summarize the latest commits in this repo"
ai chat "Explain the difference between RAG and fine-tuning"
ai status        # check if service is running
ai logs          # follow live logs
ai restart       # restart the service
ai stop          # stop the service
```

### Uninstall

```bash
sudo bash scripts/uninstall.sh
```

---

## Local Models (Ollama)

Run open-source LLMs locally — no API key required.

### 1. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a model

```bash
# Via terminal
ollama pull llama3.2

# Or via the dashboard: Models tab → Pull
```

### 3. Select a model

Pick any model from the **Models** tab or the navbar selector. All chat and task calls route automatically.

**Routing logic:**
- Model name starts with `claude-` → Anthropic API
- Anything else (e.g. `llama3.2`, `mistral`) → Ollama

```env
# .env
OLLAMA_URL=http://localhost:11434
LOCAL_MODEL=llama3.2
```

**Supported models to pull:**

| Model | Size | Best for |
|---|---|---|
| `llama3.2` | 3B | Fast general tasks |
| `llama3.1` | 8B | Balanced |
| `mistral` | 7B | Instruction following |
| `qwen2.5-coder` | 7B | Code generation |
| `deepseek-r1` | 7B | Reasoning |
| `phi4` | 14B | Microsoft — efficient |
| `gemma2` | 9B | Google — quality |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/task` | Submit async task → `task_id` |
| GET | `/api/task/<id>` | Poll task status + output |
| GET | `/api/task/<id>/stream` | SSE stream of task output |
| POST | `/api/task/run` | Synchronous task execution |
| GET | `/api/tasks` | List recent tasks |
| POST | `/api/chat` | Multi-turn chat |
| POST | `/api/chat/persona` | Chat with a specific persona |
| POST | `/api/chat/clear` | Clear session history |
| POST | `/api/memory` | Store a memory |
| POST | `/api/memory/search` | Semantic memory search |
| POST | `/api/rag/upload` | Upload a document |
| POST | `/api/rag/query` | Query uploaded documents |
| GET | `/api/rag/documents` | List documents |
| DELETE | `/api/rag/documents` | Delete a document |
| POST | `/api/vision/analyze` | Analyze image (file or URL) |
| POST | `/api/vision/ocr` | Extract text from image |
| POST | `/api/data/upload` | Upload CSV/Excel |
| POST | `/api/data/analyze` | AI analysis of data |
| POST | `/api/data/chart` | Generate a chart |
| GET | `/api/personas` | List personas |
| POST | `/api/personas` | Create persona |
| DELETE | `/api/personas/<id>` | Delete persona |
| GET | `/api/templates` | List templates |
| POST | `/api/templates` | Create template |
| POST | `/api/templates/<id>/run` | Run template |
| POST | `/api/templates/<id>/render` | Preview template |
| POST | `/api/batch` | Run tasks in parallel |
| POST | `/api/scheduler/jobs` | Schedule a cron job |
| GET | `/api/scheduler/jobs` | List scheduled jobs |
| DELETE | `/api/scheduler/jobs/<id>` | Delete a job |
| GET | `/api/models` | List all models (Claude + Ollama) |
| GET | `/api/models/local` | List local Ollama models |
| POST | `/api/models/pull` | Pull an Ollama model (SSE stream) |
| POST | `/api/models/delete` | Delete a local model |
| GET | `/api/monitoring/stats` | Usage statistics |
| GET | `/api/monitoring/requests` | Recent request log |
| GET | `/api/monitoring/hourly` | Hourly usage summary |
| POST | `/api/auth/login` | Get JWT token |
| POST | `/api/db/query` | Execute SQL query (sandboxed) |
| POST | `/api/browser/screenshot` | Capture webpage screenshot |
| POST | `/api/browser/extract` | Extract webpage content |

---

## Configuration

All settings are read from `.env` at startup.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Anthropic API key |
| `MODEL` | `claude-opus-4-7` | Default Claude model |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `LOCAL_MODEL` | `llama3.2` | Default local model |
| `SECRET_KEY` | `dev-secret-…` | JWT signing key |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `5000` | Server port |
| `DEBUG` | `false` | Flask debug mode |
| `MAX_TOKENS` | `16000` | Max tokens per response |
| `MAX_AGENT_ITERATIONS` | `30` | Max agentic loop steps |
| `BASH_TIMEOUT` | `30` | Shell command timeout (s) |
| `WEB_TIMEOUT` | `15` | HTTP fetch timeout (s) |
| `CHROMADB_PATH` | `./data/chromadb` | Vector store path |
| `AUTH_DISABLED` | `true` | Disable JWT auth |
| `ADMIN_USER` | `admin` | Admin username |
| `ADMIN_PASS` | `admin123` | Admin password |
| `DATABASE_URL` | SQLite | PostgreSQL connection string |
| `SMTP_HOST` | — | Email SMTP host |
| `SLACK_WEBHOOK_URL` | — | Slack notifications |
| `DISCORD_WEBHOOK_URL` | — | Discord notifications |

---

## Agent Tools

The agentic loop has access to these built-in tools:

| Tool | Description |
|---|---|
| `execute_bash` | Shell commands with timeout and safety blocklist |
| `read_file` | Read file contents |
| `write_file` | Write / append to files |
| `search_files` | Glob pattern file search |
| `web_fetch` | HTTP fetch with content extraction |
| `memory_store` | Persist information in ChromaDB |
| `memory_search` | Semantic search over stored memories |

---

## Security

- Bash commands blocked against a safety blocklist before execution
- SQL queries blocked for injection patterns (UNION SELECT, stacked queries, inline comments)
- Python sandbox blocks `os`, `subprocess`, `socket`, and other dangerous imports
- Rate limiting: token-bucket per IP address
- JWT authentication (disabled by default — enable with `AUTH_DISABLED=false`)
- Web fetch timeout prevents hung requests

---

## Docker

```bash
docker compose up --build
# Dashboard at http://localhost:5000
```

---

## Tech Stack

- **AI**: Anthropic Claude Opus 4.7, Ollama (local LLMs)
- **Backend**: Python 3.11+, Flask, APScheduler
- **Vector DB**: ChromaDB (cosine similarity)
- **Browser automation**: Playwright
- **Charts**: matplotlib
- **Auth**: HMAC-HS256 JWT
- **Frontend**: Vanilla JS, CSS custom properties
- **Infra**: systemd, Docker / docker-compose
