"""
Reminder management service.

Handles creation, retrieval, and cancellation of reminders.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
import logging

from ..models import Reminder, TaskStatus, User
from ..services.time_parser import parse_time_expression, extract_time_from_text

logger = logging.getLogger(__name__)


def _schedule_reminder_task(reminder_id: int, scheduled_time: datetime):
    """
    Helper to schedule a reminder task without circular import.
    Uses Celery's task registry to find and call the task.
    """
    try:
        from ..celery_app import celery_app
        task = celery_app.tasks.get("backend.tasks.reminder_tasks.schedule_reminder")
        if task:
            task.delay(reminder_id, scheduled_time)
        else:
            logger.error("schedule_reminder task not found in Celery registry")
    except Exception as e:
        logger.error(f"Failed to schedule reminder task: {e}")


def create_reminder_from_text(
    db: Session,
    user_id: int,
    text: str,
    timezone: str = "America/Toronto"
) -> Optional[Reminder]:
    """
    Create a reminder from natural language text.
    
    Examples:
        - "Remind me to call mom at 3pm"
        - "Set reminder for tomorrow morning to buy groceries"
        - "Remind me in 2 hours to take medicine"
    
    Args:
        db: Database session
        user_id: User ID
        text: Natural language reminder text
        timezone: User's timezone
        
    Returns:
        Created Reminder object or None if time parsing fails
    """
    # Extract time from text
    scheduled_time = extract_time_from_text(text, timezone)
    
    if not scheduled_time:
        logger.error(f"❌ Could not extract time from: '{text}'")
        return None
    
    # Extract reminder content (remove time-related phrases)
    content = text
    
    # Common phrases to remove for cleaner content
    remove_phrases = [
        "remind me to", "remind me", "set a reminder to", "set reminder",
        "set a reminder for", "reminder to", "reminder for"
    ]
    
    content_lower = content.lower()
    for phrase in remove_phrases:
        if phrase in content_lower:
            # Find the phrase and remove it
            idx = content_lower.find(phrase)
            content = content[:idx] + content[idx + len(phrase):]
            break
    
    # Clean up content
    content = content.strip()
    
    # If content is empty, use original text
    if not content:
        content = text
    
    # Create reminder
    reminder = Reminder(
        user_id=user_id,
        content=content,
        scheduled_time=scheduled_time,
        status=TaskStatus.PENDING.value,
        context={"original_text": text, "timezone": timezone}
    )
    
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    
    logger.info(f"✅ Created reminder ID {reminder.id}: '{content}' at {scheduled_time}")
    
    # Schedule the reminder task
    try:
        schedule_reminder.delay(reminder.id, scheduled_time)
        logger.info(f"📅 Scheduled Celery task for reminder {reminder.id}")
    except Exception as e:
        logger.error(f"❌ Failed to schedule Celery task: {e}")
    
    return reminder


def create_reminder(
    db: Session,
    user_id: int,
    content: str,
    scheduled_time: datetime,
    recurring: bool = False,
    recurrence_pattern: Optional[str] = None
) -> Reminder:
    """
    Create a reminder with explicit datetime.
    
    Args:
        db: Database session
        user_id: User ID
        content: Reminder content
        scheduled_time: When to trigger the reminder
        recurring: Whether this is a recurring reminder
        recurrence_pattern: Pattern for recurring reminders
        
    Returns:
        Created Reminder object
    """
    reminder = Reminder(
        user_id=user_id,
        content=content,
        scheduled_time=scheduled_time,
        status=TaskStatus.PENDING.value,
        recurring=recurring,
        recurrence_pattern=recurrence_pattern
    )
    
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    
    # Schedule the reminder
    try:
        schedule_reminder.delay(reminder.id, scheduled_time)
    except Exception as e:
        logger.error(f"Failed to schedule reminder: {e}")
    
    return reminder


def get_user_reminders(
    db: Session,
    user_id: int,
    status: Optional[TaskStatus] = None,
    limit: int = 50
) -> List[Reminder]:
    """
    Get reminders for a user.
    
    Args:
        db: Database session
        user_id: User ID
        status: Filter by status (optional)
        limit: Maximum number of reminders to return
        
    Returns:
        List of Reminder objects
    """
    query = db.query(Reminder).filter(Reminder.user_id == user_id)
    
    if status:
        query = query.filter(Reminder.status == status.value)
    
    query = query.order_by(Reminder.scheduled_time.desc()).limit(limit)
    
    return query.all()


def cancel_reminder(db: Session, reminder_id: int, user_id: int) -> bool:
    """
    Cancel a pending reminder.
    
    Args:
        db: Database session
        reminder_id: Reminder ID
        user_id: User ID (for security check)
        
    Returns:
        True if cancelled successfully, False otherwise
    """
    reminder = (
        db.query(Reminder)
        .filter(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id
        )
        .first()
    )
    
    if not reminder:
        logger.warning(f"⚠️  Reminder {reminder_id} not found for user {user_id}")
        return False
    
    if reminder.status != TaskStatus.PENDING.value:
        logger.warning(f"⚠️  Reminder {reminder_id} is not pending (status: {reminder.status})")
        return False
    
    reminder.status = TaskStatus.CANCELLED.value
    db.commit()
    
    logger.info(f"✅ Cancelled reminder {reminder_id}")
    
    # TODO: Revoke the Celery task if possible
    
    return True


def get_upcoming_reminders(db: Session, user_id: int, limit: int = 10) -> List[Reminder]:
    """
    Get upcoming pending reminders for a user.
    
    Args:
        db: Database session
        user_id: User ID
        limit: Maximum number to return
        
    Returns:
        List of upcoming Reminder objects
    """
    now = datetime.utcnow()
    
    return (
        db.query(Reminder)
        .filter(
            Reminder.user_id == user_id,
            Reminder.status == TaskStatus.PENDING.value,
            Reminder.scheduled_time >= now
        )
        .order_by(Reminder.scheduled_time.asc())
        .limit(limit)
        .all()
    )