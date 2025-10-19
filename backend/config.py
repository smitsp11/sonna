"""
Configuration settings for the Sonna backend.

This module loads environment variables and provides configuration
for different components of the application.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Any


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Sonna Backend"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # API
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-here"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    # Gemini (LLM)
    GEMINI_API_KEY: str | None = None

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # Database (PostgreSQL / Supabase)
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/sonna"

    # Pinecone (Vector Storage)
    PINECONE_API_KEY: str = "your-pinecone-api-key"
    PINECONE_ENVIRONMENT: str = "us-west1-gcp"
    PINECONE_INDEX_NAME: str = "sonna-memories"

    # ElevenLabs (Text-to-Speech)
    ELEVENLABS_API_KEY: str = "your-elevenlabs-api-key"
    DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    # Vapi (Voice API / STT Integration)
    VAPI_API_KEY: str = "your-vapi-api-key"

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str] | str:
        """Parse CORS origins from environment variables."""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)


# Initialize global settings instance
settings = Settings()

# Logging configuration
LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "simple": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}
