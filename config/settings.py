import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # ---------------------------
    # ✅ API Keys
    # ---------------------------
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ---------------------------
    # ✅ Elasticsearch Configuration
    # ---------------------------
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    ELASTICSEARCH_INDEX: str = os.getenv("ELASTICSEARCH_INDEX", "customer_support_kb")

    # ---------------------------
    # ✅ Embedding Model Configuration
    # ---------------------------
    EMBEDDING_MODEL: str = "mixedbread-ai/mxbai-embed-large-v1"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 5

    # ---------------------------
    # ✅ LLM Configuration
    # ---------------------------
    GEMINI_MODEL: str = "gemini-1.5-pro"
    TEMPERATURE: float = 0.1
    MAX_TOKENS: int = 1000

    # ---------------------------
    # ✅ Application Configuration
    # ---------------------------
    FASTAPI_HOST: str = "0.0.0.0"
    FASTAPI_PORT: int = 8000
    STREAMLIT_PORT: int = 8501
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    AUTO_RELOAD: bool = True
    DEV_MODE: bool = True
    MOCK_SERVICES: bool = False

    # ---------------------------
    # ✅ Ticket System Configuration
    # ---------------------------
    MAX_CONCURRENT_TICKETS: int = 10
    KNOWLEDGE_SEARCH_LIMIT: int = 5
    MIN_CONFIDENCE_THRESHOLD: float = 0.3

    HIGH_PRIORITY_KEYWORDS: list[str] = [
        "urgent", "critical", "down", "broken", "error", "bug",
        "payment", "billing", "security", "hack", "breach"
    ]

    ESCALATION_KEYWORDS: list[str] = [
        "manager", "supervisor", "complain", "angry", "frustrated",
        "legal", "lawsuit", "refund", "cancel", "unsubscribe"
    ]

    # ---------------------------
    # ✅ Response Templates
    # ---------------------------
    GREETING_TEMPLATE: str = "Hello! I'm here to help you with your inquiry."
    ESCALATION_TEMPLATE: str = "I understand your concern. Let me connect you with a specialist who can better assist you."

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
