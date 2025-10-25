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
from typing import Optional, Dict, Any
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversation", tags=["conversation"])

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


def generate_gemini_response(
    user_text: str,
    conversation_context: list[Dict[str, str]] = None,
    user_timezone: str = "America/Toronto"
) -> str:
    """
    Generate a reasoning-based response using Google's Gemini API.
    
    Args:
        user_text: Current user input
        conversation_context: Previous messages for context
        user_timezone: User's timezone for date/time info
        
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
- Year: 2024

Instructions:
- Use the EXACT date and time provided above when answering date/time questions
- Be concise and natural for voice conversation
- Keep responses under 3 sentences when possible unless more detail is needed
- Be warm, helpful, and conversational
- Remember context from previous messages in this conversation"""

        # Create model
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        # If we have conversation context, include it
        if conversation_context:
            # Build conversation history
            chat_history = []
            for msg in conversation_context:
                role = "user" if msg["role"] == "user" else "model"
                chat_history.append({
                    "role": role,
                    "parts": [msg["content"]]
                })
            
            # Start chat with history
            chat = model.start_chat(history=chat_history)
            
            # Send current message with system context
            response = chat.send_message(f"{system_prompt}\n\nUser: {user_text}")
        else:
            # No history, just send the message
            response = model.generate_content(f"{system_prompt}\n\nUser: {user_text}")
        
        response_text = response.text.strip() if hasattr(response, "text") else str(response)
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
                user_text=user_text,
                conversation_context=context,
                user_timezone="America/Toronto"
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