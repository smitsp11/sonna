"""
Database models for Sonna.

This module defines SQLAlchemy ORM models and Pydantic schemas
for request/response validation.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from .database import Base


# ==================== ENUMS ====================

class TaskStatus(str, PyEnum):
    """Status of a scheduled task."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MemoryType(str, PyEnum):
    """Types of memories stored in the system."""
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    TASK = "task"
    CONVERSATION = "conversation"


class MessageRole(str, PyEnum):
    """Role of the message sender."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ==================== DATABASE MODELS (SQLAlchemy) ====================

class User(Base):
    """User model - represents a person using Sonna."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Preferences stored as JSON
    preferences = Column(JSON, default=dict)
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, name='{self.name}')>"


class Conversation(Base):
    """Conversation model - represents a chat session."""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Conversation metadata
    extra_data = Column(JSON, default={})
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class Message(Base):
    """Message model - represents a single message in a conversation."""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Optional: Store audio file path if this was a voice message
    audio_file_path = Column(String, nullable=True)
    
    # Message metadata (sentiment, etc.)
    extra_data = Column(JSON, default={})
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, role='{self.role}', content='{self.content[:30]}...')>"


class Memory(Base):
    """Memory model - represents a stored fact or preference."""
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    memory_type = Column(String, nullable=False)  # 'fact', 'preference', 'event', etc.
    source = Column(String, nullable=True)  # Where this memory came from
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Vector embedding for semantic search (stored as JSON array)
    embedding = Column(JSON, nullable=True)
    
    # Additional metadata
    extra_data = Column(JSON, default={})
    
    # Pinecone ID (if stored in Pinecone)
    pinecone_id = Column(String, nullable=True, unique=True)
    
    # Relationships
    user = relationship("User", back_populates="memories")
    
    def __repr__(self):
        return f"<Memory(id={self.id}, type='{self.memory_type}', content='{self.content[:30]}...')>"


class Reminder(Base):
    """Reminder model - represents a scheduled task or reminder."""
    __tablename__ = "reminders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String, default=TaskStatus.PENDING.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # For recurring reminders
    recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String, nullable=True)  # 'daily', 'weekly', 'monthly'
    
    # Additional context
    context = Column(JSON, default={})
    
    # Celery task ID (for background job tracking)
    task_id = Column(String, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="reminders")
    
    def __repr__(self):
        return f"<Reminder(id={self.id}, content='{self.content[:30]}...', scheduled={self.scheduled_time})>"


# ==================== PYDANTIC SCHEMAS (API Request/Response) ====================

# User Schemas
class UserBase(BaseModel):
    """Base user schema."""
    name: str
    email: str


class UserCreate(UserBase):
    """Schema for creating a new user."""
    preferences: Optional[Dict[str, Any]] = {}


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    created_at: datetime
    preferences: Dict[str, Any]
    
    class Config:
        from_attributes = True


# Conversation Schemas
class ConversationCreate(BaseModel):
    """Schema for creating a conversation."""
    title: Optional[str] = "New Conversation"


class ConversationResponse(BaseModel):
    """Schema for conversation response."""
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Message Schemas
class MessageCreate(BaseModel):
    """Schema for creating a message."""
    conversation_id: int
    role: MessageRole
    content: str
    audio_file_path: Optional[str] = None


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Memory Schemas
class MemoryCreate(BaseModel):
    """Schema for creating a memory."""
    content: str
    memory_type: MemoryType
    source: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = {}


class MemoryResponse(BaseModel):
    """Schema for memory response."""
    id: int
    user_id: int
    content: str
    memory_type: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Reminder Schemas
class ReminderCreate(BaseModel):
    """Schema for creating a reminder."""
    content: str
    scheduled_time: datetime
    recurring: Optional[bool] = False
    recurrence_pattern: Optional[str] = None
    context: Optional[Dict[str, Any]] = {}


class ReminderResponse(BaseModel):
    """Schema for reminder response."""
    id: int
    user_id: int
    content: str
    scheduled_time: datetime
    status: str
    created_at: datetime
    recurring: bool
    
    class Config:
        from_attributes = True


# Assistant Response
class AssistantResponse(BaseModel):
    """Standard response format for assistant interactions."""
    text: str = Field(..., description="Text response from the assistant")
    actions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of actions to take (e.g., create_reminder)"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Updated context for the conversation"
    )