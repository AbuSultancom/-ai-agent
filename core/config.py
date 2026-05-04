import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Anthropic / Claude ─────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "claude-opus-4-7")

    # ── Local models via Ollama ────────────────────────────────────────────────
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    LOCAL_MODEL: str = os.getenv("LOCAL_MODEL", "llama3.2")

    # ── Server ─────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ── Agent loop ─────────────────────────────────────────────────────────────
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16000"))
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "30"))
    BASH_TIMEOUT: int = int(os.getenv("BASH_TIMEOUT", "30"))
    WEB_TIMEOUT: int = int(os.getenv("WEB_TIMEOUT", "15"))

    # ── Memory ─────────────────────────────────────────────────────────────────
    CHROMADB_PATH: str = os.getenv("CHROMADB_PATH", "./data/chromadb")

    # ── E-commerce Database ────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/ecommerce.db")


config = Config()
