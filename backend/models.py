"""
Data models for the Sonna backend.

This module defines Pydantic models for request/response validation
and database interactions.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class TaskStatus(str, Enum):
    """Status of a scheduled task."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class MemoryType(str, Enum):
    """Types of memories stored in the system."""
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    TASK = "task"

class ReminderBase(BaseModel):
    """Base model for reminders."""
    content: str = Field(..., description="Content of the reminder")
    scheduled_time: datetime = Field(..., description="When the reminder should trigger")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for the reminder"
    )

class ReminderCreate(ReminderBase):
    """Schema for creating a new reminder."""
    pass

class Reminder(ReminderBase):
    """Schema for reminder responses."""
    id: str = Field(..., description="Unique identifier for the reminder")
    created_at: datetime = Field(..., description="When the reminder was created")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current status of the reminder")
    
    class Config:
        orm_mode = True

class MemoryBase(BaseModel):
    """Base model for memories."""
    content: str = Field(..., description="Content of the memory")
    memory_type: MemoryType = Field(..., description="Type of memory")
    source: str = Field(..., description="Source of the memory")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

class MemoryCreate(MemoryBase):
    """Schema for creating a new memory."""
    pass

class Memory(MemoryBase):
    """Schema for memory responses."""
    id: str = Field(..., description="Unique identifier for the memory")
    created_at: datetime = Field(..., description="When the memory was created")
    embedding: Optional[List[float]] = Field(
        None,
        description="Vector embedding of the memory content"
    )
    
    class Config:
        orm_mode = True

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
