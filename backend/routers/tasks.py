"""
Task and reminder API endpoints.

Provides CRUD operations for managing reminders and scheduled tasks.
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

from ..database import get_db
from ..models import Reminder, TaskStatus
from ..services.user_service import get_or_create_default_user
from ..services.reminder_service import (
    create_reminder_from_text,
    create_reminder,
    get_user_reminders,
    cancel_reminder,
    get_upcoming_reminders
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


class ReminderCreateFromText(BaseModel):
    """Schema for creating a reminder from natural language."""
    text: str
    timezone: Optional[str] = "America/Toronto"


class ReminderCreateExplicit(BaseModel):
    """Schema for creating a reminder with explicit datetime."""
    content: str
    scheduled_time: datetime
    recurring: Optional[bool] = False
    recurrence_pattern: Optional[str] = None


class ReminderListResponse(BaseModel):
    """Response schema for listing reminders."""
    reminders: List[dict]
    total: int


@router.post("/reminders/from-text", response_model=dict)
async def create_reminder_from_natural_language(
    data: ReminderCreateFromText,
    db: Session = Depends(get_db)
):
    """
    Create a reminder from natural language text.
    
    Examples:
        - "Remind me to call mom at 3pm"
        - "Set reminder for tomorrow morning to exercise"
        - "Remind me in 2 hours to take medicine"
    """
    try:
        user = get_or_create_default_user(db)
        
        reminder = create_reminder_from_text(
            db=db,
            user_id=user.id,
            text=data.text,
            timezone=data.timezone
        )
        
        if not reminder:
            raise HTTPException(
                status_code=400,
                detail="Could not parse time from text. Please be more specific about when you want the reminder."
            )
        
        return {
            "id": reminder.id,
            "content": reminder.content,
            "scheduled_time": reminder.scheduled_time,
            "status": reminder.status,
            "message": f"Reminder set for {reminder.scheduled_time.strftime('%A, %B %d at %I:%M %p')}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reminders", response_model=dict)
async def create_reminder_explicit(
    data: ReminderCreateExplicit,
    db: Session = Depends(get_db)
):
    """
    Create a reminder with explicit datetime.
    
    For programmatic creation or when you already have a parsed datetime.
    """
    try:
        user = get_or_create_default_user(db)
        
        reminder = create_reminder(
            db=db,
            user_id=user.id,
            content=data.content,
            scheduled_time=data.scheduled_time,
            recurring=data.recurring or False,
            recurrence_pattern=data.recurrence_pattern
        )
        
        return {
            "id": reminder.id,
            "content": reminder.content,
            "scheduled_time": reminder.scheduled_time,
            "status": reminder.status,
            "recurring": reminder.recurring
        }
        
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reminders", response_model=ReminderListResponse)
async def list_reminders(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    List all reminders for the current user.
    
    Query params:
        - status: Filter by status (pending, completed, failed, cancelled)
        - limit: Maximum number of reminders to return
    """
    try:
        user = get_or_create_default_user(db)
        
        # Parse status if provided
        status_filter = None
        if status:
            try:
                status_filter = TaskStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {[s.value for s in TaskStatus]}"
                )
        
        reminders = get_user_reminders(
            db=db,
            user_id=user.id,
            status=status_filter,
            limit=limit
        )
        
        reminder_list = [
            {
                "id": r.id,
                "content": r.content,
                "scheduled_time": r.scheduled_time,
                "status": r.status,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "recurring": r.recurring
            }
            for r in reminders
        ]
        
        return {
            "reminders": reminder_list,
            "total": len(reminder_list)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reminders/upcoming", response_model=ReminderListResponse)
async def list_upcoming_reminders(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Get upcoming pending reminders.
    
    Returns only pending reminders scheduled for the future,
    sorted by scheduled time (soonest first).
    """
    try:
        user = get_or_create_default_user(db)
        
        reminders = get_upcoming_reminders(
            db=db,
            user_id=user.id,
            limit=limit
        )
        
        reminder_list = [
            {
                "id": r.id,
                "content": r.content,
                "scheduled_time": r.scheduled_time,
                "status": r.status,
                "created_at": r.created_at
            }
            for r in reminders
        ]
        
        return {
            "reminders": reminder_list,
            "total": len(reminder_list)
        }
        
    except Exception as e:
        logger.error(f"Failed to get upcoming reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/reminders/{reminder_id}")
async def cancel_reminder_endpoint(
    reminder_id: int,
    db: Session = Depends(get_db)
):
    """
    Cancel a pending reminder.
    
    Only pending reminders can be cancelled.
    """
    try:
        user = get_or_create_default_user(db)
        
        success = cancel_reminder(
            db=db,
            reminder_id=reminder_id,
            user_id=user.id
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Reminder not found or cannot be cancelled"
            )
        
        return {
            "status": "success",
            "message": f"Reminder {reminder_id} cancelled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reminders/{reminder_id}")
async def get_reminder_detail(
    reminder_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific reminder."""
    try:
        user = get_or_create_default_user(db)
        
        reminder = (
            db.query(Reminder)
            .filter(
                Reminder.id == reminder_id,
                Reminder.user_id == user.id
            )
            .first()
        )
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        
        return {
            "id": reminder.id,
            "content": reminder.content,
            "scheduled_time": reminder.scheduled_time,
            "status": reminder.status,
            "created_at": reminder.created_at,
            "completed_at": reminder.completed_at,
            "recurring": reminder.recurring,
            "recurrence_pattern": reminder.recurrence_pattern,
            "context": reminder.context
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get reminder detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ReminderUpdate(BaseModel):
    """Schema for updating a reminder."""
    content: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None


@router.put("/reminders/{reminder_id}")
async def update_reminder(
    reminder_id: int,
    update_data: ReminderUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing reminder."""
    try:
        user = get_or_create_default_user(db)
        
        reminder = (
            db.query(Reminder)
            .filter(
                Reminder.id == reminder_id,
                Reminder.user_id == user.id
            )
            .first()
        )
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        
        # Only allow updating pending reminders
        if reminder.status != TaskStatus.PENDING.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update reminder with status: {reminder.status}"
            )
        
        # Update fields
        if update_data.content is not None:
            reminder.content = update_data.content
        
        if update_data.scheduled_time is not None:
            reminder.scheduled_time = update_data.scheduled_time
            # Reschedule the Celery task
            try:
                from ..tasks.reminder_tasks import schedule_reminder
                schedule_reminder.delay(reminder.id, update_data.scheduled_time)
                logger.info(f"📅 Rescheduled reminder {reminder.id}")
            except Exception as e:
                logger.error(f"Failed to reschedule reminder: {e}")
        
        if update_data.recurring is not None:
            reminder.recurring = update_data.recurring
        
        if update_data.recurrence_pattern is not None:
            reminder.recurrence_pattern = update_data.recurrence_pattern
        
        db.commit()
        db.refresh(reminder)
        
        return {
            "id": reminder.id,
            "content": reminder.content,
            "scheduled_time": reminder.scheduled_time,
            "status": reminder.status,
            "recurring": reminder.recurring,
            "recurrence_pattern": reminder.recurrence_pattern,
            "message": f"Reminder {reminder_id} updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))