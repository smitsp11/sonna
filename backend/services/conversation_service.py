"""
Conversation management service for Sonna.

Handles conversation creation, message storage, and context retrieval.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..models import Conversation, Message, User, MessageRole


def get_or_create_active_conversation(db: Session, user_id: int) -> Conversation:
    """
    Get the user's most recent active conversation or create a new one.
    
    A conversation is considered "active" if it was updated in the last 2 hours.
    
    Args:
        db: Database session
        user_id: User ID
        
    Returns:
        Conversation object
    """
    # Check for recent conversation (within last 2 hours)
    two_hours_ago = datetime.utcnow() - timedelta(hours=2)
    
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.updated_at >= two_hours_ago
        )
        .order_by(desc(Conversation.updated_at))
        .first()
    )
    
    if not conversation:
        # Create new conversation
        conversation = Conversation(
            user_id=user_id,
            title=f"Conversation at {datetime.utcnow().strftime('%I:%M %p')}",
            metadata={"source": "voice"}
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    
    return conversation


def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    audio_file_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Message:
    """
    Add a message to a conversation.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        role: Message role ('user', 'assistant', 'system')
        content: Message content
        audio_file_path: Optional path to audio file
        metadata: Optional metadata dictionary
        
    Returns:
        Created Message object
    """
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        audio_file_path=audio_file_path,
        metadata=metadata or {}
    )
    
    db.add(message)
    
    # Update conversation's updated_at timestamp
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conversation:
        conversation.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(message)
    
    return message


def get_conversation_context(
    db: Session,
    conversation_id: int,
    limit: int = 10
) -> List[Dict[str, str]]:
    """
    Get recent messages from a conversation for context.
    
    Returns messages in format suitable for Gemini API:
    [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        limit: Maximum number of messages to retrieve
        
    Returns:
        List of message dictionaries
    """
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(limit)
        .all()
    )
    
    # Reverse to get chronological order
    messages = list(reversed(messages))
    
    # Format for Gemini
    context = []
    for msg in messages:
        context.append({
            "role": msg.role,
            "content": msg.content
        })
    
    return context


def get_conversation_history(db: Session, user_id: int, limit: int = 5) -> List[Conversation]:
    """
    Get user's recent conversations.
    
    Args:
        db: Database session
        user_id: User ID
        limit: Maximum number of conversations to retrieve
        
    Returns:
        List of Conversation objects
    """
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
        .all()
    )


def generate_conversation_title(db: Session, conversation_id: int, first_message: str) -> None:
    """
    Generate a title for the conversation based on the first user message.
    
    Args:
        db: Database session
        conversation_id: Conversation ID
        first_message: First user message content
    """
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    if conversation and conversation.title.startswith("Conversation at"):
        # Generate title from first message (first 50 chars)
        title = first_message[:50]
        if len(first_message) > 50:
            title += "..."
        
        conversation.title = title
        db.commit()


def search_conversations(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search past conversations for specific topics or keywords.
    
    Uses case-insensitive text search to find messages containing the query.
    Returns conversations with matching messages, including context snippets.
    
    Args:
        db: Database session
        user_id: User ID
        query: Search query string
        limit: Maximum number of results to return
        
    Returns:
        List of dictionaries with conversation info and matching message snippets
    """
    # Search for messages containing the query (case-insensitive)
    search_pattern = f"%{query}%"
    
    matching_messages = (
        db.query(Message, Conversation)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.user_id == user_id,
            Message.content.ilike(search_pattern)
        )
        .order_by(desc(Message.created_at))
        .limit(limit * 2)  # Get more than needed to group by conversation
        .all()
    )
    
    if not matching_messages:
        return []
    
    # Group results by conversation and format
    results = []
    seen_conversations = set()
    
    for message, conversation in matching_messages:
        if conversation.id in seen_conversations:
            continue
            
        if len(results) >= limit:
            break
            
        seen_conversations.add(conversation.id)
        
        # Extract snippet with context (50 chars before and after match)
        content_lower = message.content.lower()
        query_lower = query.lower()
        match_pos = content_lower.find(query_lower)
        
        if match_pos != -1:
            start = max(0, match_pos - 50)
            end = min(len(message.content), match_pos + len(query) + 50)
            snippet = message.content[start:end]
            
            # Add ellipsis if truncated
            if start > 0:
                snippet = "..." + snippet
            if end < len(message.content):
                snippet = snippet + "..."
        else:
            # Fallback: just use first 100 chars
            snippet = message.content[:100]
            if len(message.content) > 100:
                snippet += "..."
        
        results.append({
            "conversation_id": conversation.id,
            "conversation_title": conversation.title,
            "message_role": message.role,
            "message_snippet": snippet,
            "message_date": message.created_at.strftime("%A, %B %d at %I:%M %p"),
            "full_message": message.content
        })
    
    return results