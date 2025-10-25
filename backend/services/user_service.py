"""
User management service for Sonna.

Handles user creation, retrieval, and profile management.
"""

from typing import Optional
from sqlalchemy.orm import Session
from ..models import User


def get_or_create_default_user(db: Session) -> User:
    """
    Get the default user or create one if it doesn't exist.
    
    For now, we use a single default user. In the future, this will
    be replaced with proper authentication and multi-user support.
    
    Args:
        db: Database session
        
    Returns:
        User object
    """
    # Try to get existing default user
    user = db.query(User).filter(User.email == "default@sonna.ai").first()
    
    if not user:
        # Create default user
        user = User(
            name="Sonna User",
            email="default@sonna.ai",
            preferences={
                "timezone": "America/Toronto",
                "language": "en",
                "voice_preference": "default"
            }
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    return user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """
    Get a user by their ID.
    
    Args:
        db: Database session
        user_id: User ID
        
    Returns:
        User object or None if not found
    """
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get a user by their email.
    
    Args:
        db: Database session
        email: User email
        
    Returns:
        User object or None if not found
    """
    return db.query(User).filter(User.email == email).first()