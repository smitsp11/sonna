"""
Memory extraction service using Gemini AI.

This module extracts memorable information from conversations
and categorizes them for storage in the memory system.
"""

import logging
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from ..config import settings
from ..models import MemoryType

logger = logging.getLogger(__name__)

# Initialize Gemini for memory extraction
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    MEMORY_EXTRACTION_ENABLED = True
    logger.info("✅ Memory extraction service initialized with Gemini")
except Exception as e:
    MEMORY_EXTRACTION_ENABLED = False
    logger.error(f"❌ Failed to initialize memory extraction: {e}")


def extract_memories_from_conversation(conversation_text: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Extract memorable information from a conversation.
    
    Args:
        conversation_text: The conversation text to analyze
        user_id: ID of the user
        
    Returns:
        List of extracted memories with metadata
    """
    if not MEMORY_EXTRACTION_ENABLED:
        logger.warning("Memory extraction not enabled, returning empty list")
        return []
    
    try:
        # Create Gemini model for memory extraction
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        # Prompt for memory extraction
        extraction_prompt = f"""
Analyze the following conversation and extract any memorable information about the user.
Focus on facts, preferences, events, and tasks that should be remembered.

Conversation:
{conversation_text}

Extract memories in the following format (JSON):
{{
    "memories": [
        {{
            "content": "Brief description of what to remember",
            "type": "fact|preference|event|task",
            "importance": "high|medium|low",
            "context": "Additional context about when/why this is important"
        }}
    ]
}}

Only extract information that is:
1. Factual and verifiable
2. About the user's preferences or characteristics
3. Important events or tasks
4. Information that would be useful to remember for future conversations

Do not extract:
- Generic responses
- Temporary information
- Information that changes frequently
- Personal details that shouldn't be stored

Return only the JSON, no other text.
"""
        
        # Get extraction from Gemini
        response = model.generate_content(extraction_prompt)
        response_text = response.text.strip()
        
        # Parse the JSON response
        import json
        try:
            # Clean up the response to extract JSON
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text
            
            extraction_result = json.loads(json_text)
            memories = extraction_result.get("memories", [])
            
            # Format memories for storage
            formatted_memories = []
            for memory in memories:
                formatted_memories.append({
                    "content": memory.get("content", ""),
                    "memory_type": memory.get("type", "fact"),
                    "importance": memory.get("importance", "medium"),
                    "context": memory.get("context", ""),
                    "user_id": user_id,
                    "source": "conversation_extraction"
                })
            
            logger.info(f"🧠 Extracted {len(formatted_memories)} memories from conversation")
            return formatted_memories
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse memory extraction JSON: {e}")
            logger.debug(f"Raw response: {response_text}")
            return []
            
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}", exc_info=True)
        return []


def extract_memories_from_message(message_text: str, user_id: int, message_role: str) -> List[Dict[str, Any]]:
    """
    Extract memories from a single message.
    
    Args:
        message_text: The message text to analyze
        user_id: ID of the user
        message_role: Role of the message sender (user/assistant)
        
    Returns:
        List of extracted memories
    """
    if not MEMORY_EXTRACTION_ENABLED:
        return []
    
    # Only extract memories from user messages for now
    if message_role != "user":
        return []
    
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        extraction_prompt = f"""
Analyze this user message and extract any memorable information:

Message: "{message_text}"

Extract any facts, preferences, or important information about the user.
Return as JSON:
{{
    "memories": [
        {{
            "content": "What to remember",
            "type": "fact|preference|event|task",
            "importance": "high|medium|low"
        }}
    ]
}}

Only extract if there's actually something memorable. Return empty array if nothing worth remembering.
"""
        
        response = model.generate_content(extraction_prompt)
        response_text = response.text.strip()
        
        import json
        try:
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text
            
            extraction_result = json.loads(json_text)
            memories = extraction_result.get("memories", [])
            
            formatted_memories = []
            for memory in memories:
                formatted_memories.append({
                    "content": memory.get("content", ""),
                    "memory_type": memory.get("type", "fact"),
                    "importance": memory.get("importance", "medium"),
                    "user_id": user_id,
                    "source": "message_extraction"
                })
            
            return formatted_memories
            
        except json.JSONDecodeError:
            return []
            
    except Exception as e:
        logger.error(f"Message memory extraction failed: {e}")
        return []


def categorize_memory(content: str, memory_type: str) -> Dict[str, Any]:
    """
    Categorize and analyze a memory for better storage.
    
    Args:
        content: Memory content
        memory_type: Type of memory (fact, preference, event, task)
        
    Returns:
        Categorized memory with metadata
    """
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        categorization_prompt = f"""
Analyze this memory and provide additional categorization:

Content: "{content}"
Type: {memory_type}

Provide:
1. Key topics/tags
2. Importance level
3. Time relevance (is this time-sensitive?)
4. Relationship to other memories

Return as JSON:
{{
    "topics": ["topic1", "topic2"],
    "importance": "high|medium|low",
    "time_sensitive": true/false,
    "relationships": ["related_memory_type1", "related_memory_type2"]
}}
"""
        
        response = model.generate_content(categorization_prompt)
        response_text = response.text.strip()
        
        import json
        try:
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text
            
            categorization = json.loads(json_text)
            return categorization
            
        except json.JSONDecodeError:
            return {
                "topics": [],
                "importance": "medium",
                "time_sensitive": False,
                "relationships": []
            }
            
    except Exception as e:
        logger.error(f"Memory categorization failed: {e}")
        return {
            "topics": [],
            "importance": "medium",
            "time_sensitive": False,
            "relationships": []
        }


def should_store_memory(memory: Dict[str, Any]) -> bool:
    """
    Determine if a memory should be stored based on importance and relevance.
    
    Args:
        memory: Memory data to evaluate
        
    Returns:
        True if memory should be stored, False otherwise
    """
    # Filter criteria
    importance = memory.get("importance", "medium")
    content = memory.get("content", "").strip()
    
    # Don't store empty or very short memories
    if len(content) < 10:
        return False
    
    # Don't store low importance memories unless they're preferences
    if importance == "low" and memory.get("memory_type") != "preference":
        return False
    
    # Don't store generic responses
    generic_phrases = [
        "thank you", "okay", "sure", "yes", "no", "hello", "hi",
        "good morning", "good afternoon", "good evening"
    ]
    
    content_lower = content.lower()
    if any(phrase in content_lower for phrase in generic_phrases):
        return False
    
    return True
