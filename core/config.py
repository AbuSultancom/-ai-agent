import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "claude-opus-4-7")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
    CHROMADB_PATH: str = os.getenv("CHROMADB_PATH", "./data/chromadb")
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "16000"))
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "30"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))
    BASH_TIMEOUT: int = int(os.getenv("BASH_TIMEOUT", "30"))
    WEB_TIMEOUT: int = int(os.getenv("WEB_TIMEOUT", "15"))


config = Config()
