"""
Main FastAPI application for Sonna backend.

This module initializes the FastAPI app, includes all routers,
and sets up middleware and event handlers.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import conversation, voice, tasks, memory, tts
from .config import settings
from .database import init_db, engine
from . import models

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sonna API",
    description="Backend API for Sonna personal assistant",
    version="0.1.0"
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("🚀 Starting Sonna backend...")
    
    # Initialize database - create tables if they don't exist
    try:
        init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    logger.info("✅ Sonna backend started successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("👋 Shutting down Sonna backend...")
    engine.dispose()
    logger.info("✅ Database connections closed")


# Include routers
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(tts.router, prefix="/api/tts", tags=["tts"])
app.include_router(conversation.router, prefix="/conversation", tags=["Conversation"])


@app.get("/")
async def root():
    """Root endpoint that returns a welcome message."""
    return {
        "message": "Welcome to Sonna API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "database": "connected"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)