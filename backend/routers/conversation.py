"""
Conversation loop endpoint: voice → reasoning → voice.
Handles user audio input, generates a thoughtful response via Gemini,
and returns spoken output as audio.
"""

import io
import os
import tempfile
import logging
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO

import google.generativeai as genai
from fastapi import APIRouter, UploadFile, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..routers.voice import transcribe_audio
from ..routers.tts import generate_tts, TTSRequest as TTSRequestModel
from ..config import settings

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


def generate_default_response() -> str:
    """Fallback message when Gemini API is unavailable."""
    return "I'm sorry, I can’t think right now. Please check my AI connection."


def generate_gemini_response(user_text: str) -> str:
    """Generate a reasoning-based response using Google's Gemini API."""
    if not GEMINI_ENABLED:
        logger.warning("Gemini client not initialized, using default response")
        return generate_default_response()

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        chat = model.start_chat(history=[])
        response = chat.send_message(
            f"You are Sonna, an intelligent and caring AI voice assistant. "
            f"Be concise, natural, and helpful.\n\nUser: {user_text}"
        )
        response_text = response.text.strip() if hasattr(response, "text") else str(response)
        logger.info("✅ Successfully generated response from Gemini")
        return response_text
    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return generate_default_response()


@router.post("/voice-loop", response_model=VoiceLoopResponse)
async def voice_reasoning_loop(audio: UploadFile):
    """
    Full pipeline: speech → reasoning → speech.
    """
    temp_audio_path = None
    response_text = None

    try:
        # Step 1: Save uploaded audio temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename or "audio").suffix or ".wav") as tmp:
            contents = await audio.read()
            tmp.write(contents)
            temp_audio_path = tmp.name

        logger.info(f"Temporary audio saved to {temp_audio_path}")

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
        logger.info(f"Normalized content_type: {mime_type}")

        # Step 2: Transcribe
        transcription = await transcribe_audio(mock_upload)
        user_text = transcription.get("text", "").strip()

        if not user_text:
            user_text = "I couldn't catch that. Could you please repeat?"
            logger.warning("No speech detected in audio")
            response_text = user_text
        else:
            logger.info(f"Transcribed text: {user_text[:100]}...")
            response_text = generate_gemini_response(user_text)

        # Step 3: Generate TTS audio
        logger.info("Generating TTS audio from response...")
        tts_request = TTSRequestModel(text=response_text)
        tts_response = await generate_tts(tts_request)

        # Step 4: Return audio
        if isinstance(tts_response, StreamingResponse):
            return tts_response

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
                "X-Transcribed-Text": user_text,
                "X-Response-Text": response_text[:500],
            },
        )

    except Exception as e:
        logger.error(f"Voice reasoning loop failed: {e}", exc_info=True)
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
