"""
Main FastAPI application for Sonna backend.

This module initializes the FastAPI app, includes all routers,
and sets up middleware and event handlers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import conversation, voice, tasks, memory, tts
from .config import settings
from backend.routers import conversation

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

# Include routers
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
app.include_router(tts.router, prefix="/api/tts", tags=["tts"])
app.include_router(conversation.router, prefix="/conversation", tags=["Conversation"])

@app.get("/")
async def root():
    """Root endpoint that returns a welcome message."""
    return {"message": "Welcome to Sonna API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
