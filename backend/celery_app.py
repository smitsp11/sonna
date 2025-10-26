"""
Celery configuration for background task processing.

This module sets up Celery for handling scheduled reminders and other
background jobs.
"""

from celery import Celery
from celery.schedules import crontab
import os

# Redis connection URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "sonna",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Import tasks after app creation to avoid circular imports
celery_app.autodiscover_tasks(["backend.tasks"])

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    result_expires=3600,  # 1 hour
)

# Optional: Periodic tasks (for checking reminders)
celery_app.conf.beat_schedule = {
    "check-reminders-every-minute": {
        "task": "backend.tasks.reminder_tasks.check_pending_reminders",
        "schedule": 60.0,  # Run every 60 seconds
    },
}

if __name__ == "__main__":
    celery_app.start()