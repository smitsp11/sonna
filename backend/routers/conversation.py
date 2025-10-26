"""
Conversation loop endpoint: voice → reasoning → voice.
Handles user audio input, generates a thoughtful response via Gemini,
and returns spoken output as audio.

NOW WITH DATABASE INTEGRATION: Saves all conversations and messages!
"""

import io
import os
import tempfile
import logging
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any, List
from io import BytesIO
from datetime import datetime
import pytz

import google.generativeai as genai
from fastapi import APIRouter, UploadFile, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..routers.voice import transcribe_audio
from ..routers.tts import generate_tts, TTSRequest as TTSRequestModel
from ..config import settings
from ..database import get_db
from ..services.user_service import get_or_create_default_user
from ..services.conversation_service import (
    get_or_create_active_conversation,
    add_message,
    get_conversation_context,
    generate_conversation_title
)
from ..services.memory_extraction import extract_memories_from_message, should_store_memory
from ..services.pinecone_service import store_memory, search_memories
from ..services.llm_agent import llm_agent
from ..models import Memory, MemoryType, Conversation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversation")

# --- Gemini setup ---
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    GEMINI_ENABLED = True
    logger.info("✅ Gemini API initialized successfully")
except Exception as e:
    GEMINI_ENABLED = False
    logger.error(f"❌ Failed to initialize Gemini API: {e}", exc_info=True)


class VoiceLoopResponse(BaseModel):
    """Response model for the voice loop endpoint."""
    text: str
    audio_url: str = "/conversation/voice-loop"
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None


def generate_default_response() -> str:
    """Fallback message when Gemini API is unavailable."""
    return "I'm sorry, I can't think right now. Please check my AI connection."


async def get_relevant_memories(db: Session, user_id: int, query_text: str) -> List[Dict[str, Any]]:
    """
    Retrieve relevant memories for the current conversation.
    
    Args:
        db: Database session
        user_id: User ID
        query_text: Current user input to find relevant memories for
        
    Returns:
        List of relevant memories
    """
    try:
        # Generate embedding for the query
        query_embedding = await llm_agent.generate_embedding(query_text)
        
        # Search for relevant memories
        memories = search_memories(
            query_embedding=query_embedding,
            limit=3,  # Limit to 3 most relevant memories
            filter_metadata={"user_id": user_id}
        )
        
        return memories
        
    except Exception as e:
        logger.error(f"Failed to retrieve relevant memories: {e}")
        return []


async def extract_and_store_memories(db: Session, user_id: int, user_text: str, assistant_text: str):
    """
    Extract and store memories from the conversation.
    
    Args:
        db: Database session
        user_id: User ID
        user_text: User's message
        assistant_text: Assistant's response
    """
    try:
        # Extract memories from user message
        user_memories = extract_memories_from_message(user_text, user_id, "user")
        
        # Filter and store memories
        for memory_data in user_memories:
            if should_store_memory(memory_data):
                await store_memory_in_db(db, user_id, memory_data)
        
        # Also check if assistant response contains extractable information
        # (This could be extended to extract from assistant responses too)
        
    except Exception as e:
        logger.error(f"Failed to extract and store memories: {e}")


async def store_memory_in_db(db: Session, user_id: int, memory_data: Dict[str, Any]):
    """
    Store a memory in both database and Pinecone.
    
    Args:
        db: Database session
        user_id: User ID
        memory_data: Memory data to store
    """
    try:
        # Create memory in database
        memory = Memory(
            user_id=user_id,
            content=memory_data["content"],
            memory_type=memory_data.get("memory_type", MemoryType.FACT.value),
            source=memory_data.get("source", "conversation"),
            metadata=memory_data.get("metadata", {})
        )
        
        db.add(memory)
        db.commit()
        db.refresh(memory)
        
        # Generate embedding
        embedding = await llm_agent.generate_embedding(memory_data["content"])
        
        # Store in Pinecone
        pinecone_id = f"mem_{memory.id}"
        metadata = {
            "user_id": user_id,
            "memory_type": memory.memory_type,
            "created_at": memory.created_at.isoformat(),
            **memory_data.get("metadata", {})
        }
        
        success = store_memory(
            memory_id=pinecone_id,
            content=memory_data["content"],
            embedding=embedding,
            metadata=metadata
        )
        
        if success:
            memory.pinecone_id = pinecone_id
            db.commit()
            logger.info(f"🧠 Stored memory: {memory_data['content'][:50]}...")
        
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")


def get_reminder_functions():
    """Define function schemas for reminder operations that Gemini can call."""
    
    create_reminder = genai.protos.FunctionDeclaration(
        name="create_reminder",
        description="Create a new reminder for the user",
        parameters=genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties={
                "content": genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description="What the reminder is about"
                ),
                "time_expression": genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description="When the reminder should trigger (e.g., 'at 3pm', 'tomorrow morning', 'in 2 hours')"
                ),
                "timezone": genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description="User's timezone (default: America/Toronto)"
                )
            },
            required=["content", "time_expression"]
        )
    )
    
    list_reminders = genai.protos.FunctionDeclaration(
        name="list_reminders",
        description="Get the user's reminders",
        parameters=genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties={
                "status": genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description="Filter by status: 'pending', 'completed', 'failed', 'cancelled' (optional)"
                ),
                "limit": genai.protos.Schema(
                    type=genai.protos.Type.INTEGER,
                    description="Maximum number of reminders to return (default: 10)"
                )
            }
        )
    )
    
    cancel_reminder = genai.protos.FunctionDeclaration(
        name="cancel_reminder",
        description="Cancel a specific reminder",
        parameters=genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties={
                "reminder_id": genai.protos.Schema(
                    type=genai.protos.Type.INTEGER,
                    description="ID of the reminder to cancel"
                )
            },
            required=["reminder_id"]
        )
    )
    
    search_conversations = genai.protos.FunctionDeclaration(
        name="search_conversations",
        description="Search past conversations for specific topics, keywords, or information the user mentioned before",
        parameters=genai.protos.Schema(
            type=genai.protos.Type.OBJECT,
            properties={
                "query": genai.protos.Schema(
                    type=genai.protos.Type.STRING,
                    description="The search query or topic to look for in past conversations"
                ),
                "limit": genai.protos.Schema(
                    type=genai.protos.Type.INTEGER,
                    description="Maximum number of results to return (default: 5)"
                )
            },
            required=["query"]
        )
    )
    
    return genai.protos.Tool(
        function_declarations=[create_reminder, list_reminders, cancel_reminder, search_conversations]
    )


def execute_function_call(function_name: str, arguments: dict, db: Session) -> dict:
    """
    Execute a function call requested by Gemini.
    
    Args:
        function_name: Name of the function to execute
        arguments: Function arguments
        db: Database session
        
    Returns:
        Function execution result
    """
    logger.info(f"🎯 execute_function_call START: function={function_name}, args={arguments}")
    try:
        from ..services.user_service import get_or_create_default_user
        from ..services.reminder_service import (
            create_reminder_from_text,
            get_user_reminders,
            cancel_reminder
        )
        
        user = get_or_create_default_user(db)
        logger.info(f"🎯 Got user: {user.id}")
        
        if function_name == "create_reminder":
            content = arguments.get("content", "")
            time_expression = arguments.get("time_expression", "")
            timezone = arguments.get("timezone", "America/Toronto")
            
            logger.info(f"📝 Creating reminder: content='{content}', time='{time_expression}', timezone='{timezone}'")
            
            # Create the reminder
            reminder = create_reminder_from_text(
                db=db,
                user_id=user.id,
                text=f"{content} {time_expression}",
                timezone=timezone
            )
            
            logger.info(f"📝 Reminder creation result: {reminder}")
            
            if reminder:
                result = {
                    "success": True,
                    "reminder_id": reminder.id,
                    "content": reminder.content,
                    "scheduled_time": reminder.scheduled_time.isoformat(),
                    "message": f"Reminder created: '{reminder.content}' for {reminder.scheduled_time.strftime('%A, %B %d at %I:%M %p')}"
                }
                logger.info(f"🎯 Returning success result: {result}")
                return result
            else:
                error_result = {
                    "success": False,
                    "error": "Could not parse time from the reminder text. Please be more specific about when you want the reminder."
                }
                logger.warning(f"🎯 Returning error result: {error_result}")
                return error_result
                
        elif function_name == "list_reminders":
            status = arguments.get("status")
            limit = arguments.get("limit", 10)
            
            # Parse status if provided
            status_filter = None
            if status:
                from ..models import TaskStatus
                try:
                    status_filter = TaskStatus(status.lower())
                except ValueError:
                    return {
                        "success": False,
                        "error": f"Invalid status: {status}. Must be one of: pending, completed, failed, cancelled"
                    }
            
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
                    "scheduled_time": r.scheduled_time.isoformat(),
                    "status": r.status
                }
                for r in reminders
            ]
            
            return {
                "success": True,
                "reminders": reminder_list,
                "count": len(reminder_list)
            }
            
        elif function_name == "cancel_reminder":
            reminder_id = arguments.get("reminder_id")
            
            if not reminder_id:
                return {
                    "success": False,
                    "error": "Reminder ID is required"
                }
            
            success = cancel_reminder(
                db=db,
                reminder_id=reminder_id,
                user_id=user.id
            )
            
            if success:
                return {
                    "success": True,
                    "message": f"Reminder {reminder_id} cancelled successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Reminder not found or cannot be cancelled"
                }
        
        elif function_name == "search_conversations":
            from ..services.conversation_service import search_conversations
            
            query = arguments.get("query", "")
            limit = arguments.get("limit", 5)
            
            if not query:
                return {
                    "success": False,
                    "error": "Search query is required"
                }
            
            results = search_conversations(
                db=db,
                user_id=user.id,
                query=query,
                limit=limit
            )
            
            if results:
                # Format results for natural language response
                formatted_results = []
                for r in results:
                    formatted_results.append({
                        "date": r["message_date"],
                        "snippet": r["message_snippet"],
                        "role": r["message_role"]
                    })
                
                return {
                    "success": True,
                    "query": query,
                    "results": formatted_results,
                    "count": len(results),
                    "message": f"Found {len(results)} conversation(s) mentioning '{query}'"
                }
            else:
                return {
                    "success": True,
                    "query": query,
                    "results": [],
                    "count": 0,
                    "message": f"No conversations found mentioning '{query}'"
                }
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function_name}"
            }
            
    except Exception as e:
        logger.error(f"Function call execution failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Function execution failed: {str(e)}"
        }


def generate_gemini_response(
    user_text: str,
    conversation_context: list[Dict[str, str]] = None,
    user_timezone: str = "America/Toronto",
    db: Session = None
) -> str:
    """
    Generate a reasoning-based response using Google's Gemini API with function calling.
    
    Args:
        user_text: Current user input
        conversation_context: Previous messages for context
        user_timezone: User's timezone for date/time info
        db: Database session for function calls
        
    Returns:
        Generated response text
    """
    if not GEMINI_ENABLED:
        logger.warning("Gemini client not initialized, using default response")
        return generate_default_response()

    try:
        # Get current date/time in user's timezone
        timezone = pytz.timezone(user_timezone)
        now = datetime.now(timezone)
        current_date = now.strftime("%A, %B %d, %Y")
        current_time = now.strftime("%I:%M %p")
        day_of_week = now.strftime("%A")
        
        # Build system prompt with context
        system_prompt = f"""You are Sonna, an intelligent and caring AI voice assistant.

IMPORTANT - Current Real-Time Information:
- Date: {current_date} ({day_of_week})
- Time: {current_time}
- Location: Toronto, Ontario, Canada
- Year: 2025

CRITICAL INSTRUCTIONS FOR REMINDERS:
- When the user says "remind me", "set a reminder", or similar phrases, you MUST call the create_reminder function
- DO NOT just acknowledge or say you'll create a reminder - you MUST actually call the function
- Extract the reminder content and time expression, then call create_reminder immediately
- After calling the function successfully, give a brief natural confirmation

CONVERSATION SEARCH INSTRUCTIONS:
- When the user asks about past conversations, use the search_conversations function
- Examples: "What did we talk about yesterday?", "Did I mention anything about X?", "What did I say about Y?"
- Call search_conversations with the relevant query extracted from the user's question
- Present search results naturally, mentioning when the conversation happened and what was said

General Instructions:
- Use the EXACT date and time provided above when answering date/time questions
- Be concise and natural for voice conversation
- Keep responses under 2 sentences when possible
- Be warm, helpful, and conversational"""

        # Create model with function calling in AUTO mode
        model = genai.GenerativeModel(
            "gemini-2.0-flash-exp",
            tools=[get_reminder_functions()],
            tool_config={'function_calling_config': 'AUTO'}
        )
        
        # Limit conversation context to last 3 messages to avoid confusion
        limited_context = conversation_context[-3:] if conversation_context and len(conversation_context) > 3 else conversation_context
        
        # Always use chat for function calling (even without history)
        if limited_context:
            # Build conversation history
            chat_history = []
            for msg in limited_context:
                role = "user" if msg["role"] == "user" else "model"
                chat_history.append({
                    "role": role,
                    "parts": [msg["content"]]
                })
            
            # Start chat with history
            chat = model.start_chat(history=chat_history)
        else:
            # Start chat without history
            chat = model.start_chat()
        
        # Send current message with system context
        response = chat.send_message(f"{system_prompt}\n\nUser: {user_text}")
        
        # Check if response contains function calls
        logger.info(f"🔍 Checking response for function calls...")
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            logger.info(f"🔍 Candidate found, checking content...")
            if hasattr(candidate, 'content') and candidate.content:
                parts = candidate.content.parts
                logger.info(f"🔍 Found {len(parts)} parts in response")
                for i, part in enumerate(parts):
                    # Log what type of part this is
                    if hasattr(part, 'function_call') and part.function_call:
                        logger.info(f"🔍 Part {i}: FUNCTION_CALL detected")
                    elif hasattr(part, 'text'):
                        logger.info(f"🔍 Part {i}: TEXT detected - '{part.text[:50]}...'")
                    else:
                        logger.info(f"🔍 Part {i}: UNKNOWN type")
                    
                    if hasattr(part, 'function_call') and part.function_call:
                        # Execute the function call
                        function_call = part.function_call
                        function_name = function_call.name
                        arguments = dict(function_call.args)
                        
                        logger.info(f"🔧 Executing function: {function_name} with args: {arguments}")
                        
                        if db:
                            result = execute_function_call(function_name, arguments, db)
                            
                            # Send function result back to Gemini for natural response
                            function_response = genai.protos.Content(
                                parts=[genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=function_name,
                                        response={"result": result}
                                    )
                                )]
                            )
                            response = chat.send_message(function_response)
                            
                            logger.info(f"✅ Function {function_name} completed: {result}")
                        else:
                            logger.warning("No database session provided for function call")
                            return "I can help with reminders, but I need database access. Please try again."
        
        # Get text response (after function execution if applicable)
        try:
            response_text = response.text.strip()
        except ValueError:
            # If there's no text (shouldn't happen after function response), return a default
            response_text = "I've processed your request."
        
        logger.info(f"✅ Generated response for: {user_text[:50]}...")
        return response_text
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return generate_default_response()


@router.post("/voice-loop", response_model=VoiceLoopResponse)
async def voice_reasoning_loop(audio: UploadFile, db: Session = Depends(get_db)):
    """
    Full pipeline: speech → reasoning → speech.
    
    NOW SAVES TO DATABASE:
    - Gets or creates user
    - Gets or creates active conversation
    - Saves user message
    - Generates response with conversation context
    - Saves assistant response
    - Returns audio
    """
    temp_audio_path = None
    response_text = None
    conversation_id = None
    message_id = None
    user_text = ""  # Initialize to avoid reference errors

    try:
        # Get or create user (for now, using default user)
        user = get_or_create_default_user(db)
        logger.info(f"👤 Using user: {user.name} (ID: {user.id})")
        
        # Get or create active conversation
        conversation = get_or_create_active_conversation(db, user.id)
        conversation_id = conversation.id
        logger.info(f"💬 Using conversation ID: {conversation_id}")
        
        # Get conversation context (last 10 messages)
        context = get_conversation_context(db, conversation_id, limit=10)
        logger.info(f"📚 Loaded {len(context)} previous messages for context")
        
        # Step 1: Save uploaded audio temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename or "audio").suffix or ".wav") as tmp:
            contents = await audio.read()
            tmp.write(contents)
            temp_audio_path = tmp.name

        logger.info(f"💾 Temporary audio saved to {temp_audio_path}")

        # Step 1.5: Determine correct MIME type (fallback if missing)
        mime_type, _ = mimetypes.guess_type(temp_audio_path)
        allowed = {
            "audio/m4a", "audio/x-m4a", "audio/mp3", "audio/mpeg",
            "audio/mp4", "audio/wav", "audio/webm"
        }
        if mime_type not in allowed:
            logger.warning(f"Unknown MIME type detected: {mime_type}, forcing audio/x-m4a")
            mime_type = "audio/x-m4a"

        # Build a proper UploadFile for transcription
        audio_data = open(temp_audio_path, "rb").read()
        mock_upload = UploadFile(filename=Path(temp_audio_path).name, file=BytesIO(audio_data))
        mock_upload.__dict__["content_type"] = mime_type
        logger.info(f"🎤 Normalized content_type: {mime_type}")

        # Step 2: Transcribe
        transcription = await transcribe_audio(mock_upload)
        user_text = transcription.get("text", "").strip()

        if not user_text:
            user_text = "I couldn't catch that. Could you please repeat?"
            logger.warning("⚠️  No speech detected in audio")
            response_text = user_text
        else:
            logger.info(f"📝 Transcribed: {user_text[:100]}...")
            
            # Retrieve relevant memories for context (after transcription)
            # TEMPORARILY DISABLED: Gemini embedding quota exceeded
            # relevant_memories = await get_relevant_memories(db, user.id, user_text)
            # if relevant_memories:
            #     logger.info(f"🧠 Retrieved {len(relevant_memories)} relevant memories")
            #     # Add memories to context for Gemini
            #     memory_context = "\n".join([f"Memory: {mem['content']}" for mem in relevant_memories])
            #     user_text_with_memories = f"{user_text}\n\nRelevant memories:\n{memory_context}"
            # else:
            #     user_text_with_memories = user_text
            user_text_with_memories = user_text
            logger.info("⚠️ Memory retrieval temporarily disabled (quota exceeded)")
            
            # Save user message to database
            user_message = add_message(
                db=db,
                conversation_id=conversation_id,
                role="user",
                content=user_text,
                audio_file_path=None,  # Could save audio file path here
                metadata={"source": "voice", "transcription_confidence": 1.0}
            )
            logger.info(f"💾 Saved user message ID: {user_message.id}")
            
            # Generate title from first message
            if len(context) == 0:  # First message in conversation
                generate_conversation_title(db, conversation_id, user_text)
            
            # Generate response with context
            response_text = generate_gemini_response(
                user_text=user_text_with_memories,
                conversation_context=context,
                user_timezone="America/Toronto",
                db=db
            )
            
            # Save assistant response to database
            assistant_message = add_message(
                db=db,
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                metadata={"model": "gemini-2.0-flash-exp"}
            )
            message_id = assistant_message.id
            logger.info(f"💾 Saved assistant message ID: {message_id}")
            
            # Extract and store memories from the conversation
            # TEMPORARILY DISABLED: Gemini embedding quota exceeded
            # await extract_and_store_memories(db, user.id, user_text, response_text)
            logger.info("⚠️ Memory extraction temporarily disabled (quota exceeded)")

        # Step 3: Generate TTS audio
        logger.info("🔊 Generating TTS audio from response...")
        tts_request = TTSRequestModel(text=response_text)
        tts_response = await generate_tts(tts_request)

        # Step 4: Return audio
        if isinstance(tts_response, StreamingResponse):
            # Add custom headers with conversation info
            tts_response.headers["X-Conversation-ID"] = str(conversation_id)
            tts_response.headers["X-Message-ID"] = str(message_id) if message_id else ""
            tts_response.headers["X-Transcribed-Text"] = user_text[:500]
            tts_response.headers["X-Response-Text"] = response_text[:500]
            return tts_response

        # Fallback to gTTS
        from gtts import gTTS
        tts = gTTS(text=response_text, lang="en")
        buffer = io.BytesIO()
        tts.write_to_fp(buffer)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=sonna_response.mp3",
                "X-Conversation-ID": str(conversation_id),
                "X-Message-ID": str(message_id) if message_id else "",
                "X-Transcribed-Text": user_text[:500],
                "X-Response-Text": response_text[:500],
            },
        )

    except Exception as e:
        logger.error(f"❌ Voice reasoning loop failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voice processing failed: {e}",
        )

    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
                logger.debug(f"🧹 Cleaned up temp file: {temp_audio_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up {temp_audio_path}: {e}")


@router.get("/history")
async def get_conversation_history_endpoint(db: Session = Depends(get_db)):
    """
    Get conversation history for the current user.
    
    Returns:
        List of recent conversations with message counts
    """
    try:
        user = get_or_create_default_user(db)
        
        conversations = (
            db.query(
                db.query(Conversation)
                .filter(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
                .limit(10)
            ).all()
        )
        
        result = []
        for conv in conversations:
            message_count = len(conv.messages)
            result.append({
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "message_count": message_count
            })
        
        return {"conversations": result}
        
    except Exception as e:
        logger.error(f"Failed to get conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation/{conversation_id}")
async def get_conversation_detail(conversation_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific conversation including all messages.
    
    Args:
        conversation_id: Conversation ID
        
    Returns:
        Conversation details with all messages
    """
    try:
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        messages = [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            }
            for msg in conversation.messages
        ]
        
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": messages
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))