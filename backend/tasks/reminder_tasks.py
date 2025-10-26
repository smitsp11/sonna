"""
Celery tasks for reminder execution and notifications.

This module contains background tasks for processing reminders
and sending notifications when they are due.
"""

from datetime import datetime, timedelta
from typing import Optional
import logging
from celery import Celery
from sqlalchemy.orm import Session

from ..celery_app import celery_app
from ..database import SessionLocal
from ..models import Reminder, TaskStatus

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def schedule_reminder(self, reminder_id: int, scheduled_time_iso: str):
    """
    Schedule a reminder to be executed at the specified time.
    
    This task is called when a reminder is created and schedules
    the actual reminder execution.
    
    Args:
        reminder_id: ID of the reminder to schedule
        scheduled_time_iso: ISO format string of when the reminder should be executed
    """
    try:
        # Parse ISO string to datetime
        from datetime import timezone as dt_timezone
        from dateutil import parser as date_parser
        
        scheduled_time = date_parser.isoparse(scheduled_time_iso)
        
        # Convert to UTC and make naive (Celery expects naive UTC)
        if scheduled_time.tzinfo is None:
            # Assume it's already UTC if naive
            scheduled_time_utc = scheduled_time
        else:
            # Convert to UTC and make naive
            scheduled_time_utc = scheduled_time.astimezone(dt_timezone.utc).replace(tzinfo=None)
        
        # Calculate delay until scheduled time
        now = datetime.utcnow()
        delay_seconds = (scheduled_time_utc - now).total_seconds()
        
        logger.info(f"⏰ Scheduling reminder {reminder_id}:")
        logger.info(f"   Scheduled time (UTC): {scheduled_time_utc}")
        logger.info(f"   Current time (UTC): {now}")
        logger.info(f"   Delay: {delay_seconds} seconds ({delay_seconds/60:.1f} minutes)")
        
        if delay_seconds <= 0:
            # Reminder is already due, execute immediately
            logger.warning(f"⚠️ Reminder {reminder_id} is overdue by {abs(delay_seconds)} seconds, executing now")
            execute_reminder.delay(reminder_id)
        else:
            # Schedule the reminder execution
            execute_reminder.apply_async(
                args=[reminder_id],
                eta=scheduled_time_utc
            )
            logger.info(f"✅ Scheduled reminder {reminder_id} to execute in {delay_seconds/60:.1f} minutes")
            
    except Exception as e:
        logger.error(f"Failed to schedule reminder {reminder_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True)
def execute_reminder(self, reminder_id: int):
    """
    Execute a reminder when it's due.
    
    This task is called when a reminder's scheduled time arrives.
    It marks the reminder as completed and can trigger notifications.
    Handles recurring reminders by creating the next occurrence.
    
    Args:
        reminder_id: ID of the reminder to execute
    """
    db = SessionLocal()
    try:
        # Get the reminder
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        
        if not reminder:
            logger.error(f"Reminder {reminder_id} not found")
            return
        
        if reminder.status != TaskStatus.PENDING.value:
            logger.warning(f"Reminder {reminder_id} is not pending (status: {reminder.status})")
            return
        
        # Send notification
        logger.info(f"🔔 NOTIFICATION: {reminder.content}")
        send_reminder_notification.delay(reminder_id)
        
        # Handle recurring reminders
        if reminder.recurring and reminder.recurrence_pattern:
            logger.info(f"🔄 Processing recurring reminder: {reminder.recurrence_pattern}")
            next_time = calculate_next_occurrence(
                reminder.scheduled_time,
                reminder.recurrence_pattern
            )
            
            if next_time:
                # Create new reminder for next occurrence
                new_reminder = Reminder(
                    user_id=reminder.user_id,
                    content=reminder.content,
                    scheduled_time=next_time,
                    status=TaskStatus.PENDING.value,
                    recurring=True,
                    recurrence_pattern=reminder.recurrence_pattern,
                    context=reminder.context
                )
                db.add(new_reminder)
                db.commit()
                db.refresh(new_reminder)
                
                # Schedule the next occurrence
                schedule_reminder.delay(new_reminder.id, next_time)
                logger.info(f"✅ Created next occurrence: reminder {new_reminder.id} at {next_time}")
        
        # Mark current reminder as completed
        reminder.status = TaskStatus.COMPLETED.value
        reminder.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ Executed reminder {reminder_id}: {reminder.content}")
        
    except Exception as e:
        logger.error(f"Failed to execute reminder {reminder_id}: {e}")
        # Mark as failed
        if reminder:
            reminder.status = TaskStatus.FAILED.value
            db.commit()
        raise self.retry(exc=e, countdown=60, max_retries=3)
    finally:
        db.close()


def calculate_next_occurrence(current_time: datetime, pattern: str) -> Optional[datetime]:
    """
    Calculate the next occurrence time for a recurring reminder.
    
    Args:
        current_time: Current scheduled time
        pattern: Recurrence pattern (daily, weekly, monthly, etc.)
        
    Returns:
        Next occurrence datetime or None if pattern is invalid
    """
    pattern_lower = pattern.lower()
    
    try:
        if pattern_lower == "daily":
            return current_time + timedelta(days=1)
        elif pattern_lower == "weekly":
            return current_time + timedelta(weeks=1)
        elif pattern_lower == "monthly":
            # Add one month
            from dateutil.relativedelta import relativedelta
            try:
                return current_time + relativedelta(months=1)
            except:
                # Fallback: add 30 days
                return current_time + timedelta(days=30)
        elif pattern_lower == "yearly":
            return current_time.replace(year=current_time.year + 1)
        elif pattern_lower.startswith("every ") and "hour" in pattern_lower:
            # Parse "every X hours"
            try:
                hours = int(pattern_lower.split()[1])
                return current_time + timedelta(hours=hours)
            except:
                return None
        elif pattern_lower.startswith("every ") and "minute" in pattern_lower:
            # Parse "every X minutes"
            try:
                minutes = int(pattern_lower.split()[1])
                return current_time + timedelta(minutes=minutes)
            except:
                return None
        else:
            logger.warning(f"Unknown recurrence pattern: {pattern}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to calculate next occurrence: {e}")
        return None


@celery_app.task
def check_pending_reminders():
    """
    Periodic task to check for reminders that should be executed.
    
    This is a backup mechanism in case the scheduled tasks fail.
    It runs every minute and checks for any pending reminders
    that are past their scheduled time.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        
        # Find pending reminders that are past their scheduled time
        overdue_reminders = (
            db.query(Reminder)
            .filter(
                Reminder.status == TaskStatus.PENDING.value,
                Reminder.scheduled_time <= now
            )
            .all()
        )
        
        if overdue_reminders:
            logger.info(f"Found {len(overdue_reminders)} overdue reminders")
            
            for reminder in overdue_reminders:
                # Execute the reminder
                execute_reminder.delay(reminder.id)
                
    except Exception as e:
        logger.error(f"Failed to check pending reminders: {e}")
    finally:
        db.close()


@celery_app.task
def cleanup_old_reminders():
    """
    Clean up old completed reminders to keep the database clean.
    
    This task removes reminders that are older than 30 days
    and have been completed or cancelled.
    """
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        # Find old completed/cancelled reminders
        old_reminders = (
            db.query(Reminder)
            .filter(
                Reminder.status.in_([TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]),
                Reminder.created_at < cutoff_date
            )
            .all()
        )
        
        if old_reminders:
            logger.info(f"Cleaning up {len(old_reminders)} old reminders")
            
            for reminder in old_reminders:
                db.delete(reminder)
            
            db.commit()
            logger.info(f"✅ Cleaned up {len(old_reminders)} old reminders")
            
    except Exception as e:
        logger.error(f"Failed to cleanup old reminders: {e}")
        db.rollback()
    finally:
        db.close()


@celery_app.task
def send_reminder_notification(reminder_id: int, notification_type: str = "default"):
    """
    Send a notification for a reminder.
    
    This is a placeholder for notification logic that can be
    extended to support different notification channels.
    
    Args:
        reminder_id: ID of the reminder
        notification_type: Type of notification to send
    """
    db = SessionLocal()
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        
        if not reminder:
            logger.error(f"Reminder {reminder_id} not found for notification")
            return
        
        # TODO: Implement actual notification logic
        # This could include:
        # - Webhook notifications
        # - Email notifications
        # - Push notifications
        # - SMS notifications
        # - Slack/Discord notifications
        
        logger.info(f"📱 Sending {notification_type} notification for reminder: {reminder.content}")
        
        # For now, just log the notification
        notification_data = {
            "reminder_id": reminder_id,
            "content": reminder.content,
            "scheduled_time": reminder.scheduled_time.isoformat(),
            "notification_type": notification_type,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Notification data: {notification_data}")
        
    except Exception as e:
        logger.error(f"Failed to send notification for reminder {reminder_id}: {e}")
    finally:
        db.close()