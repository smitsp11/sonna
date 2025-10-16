"""
Text-to-Speech (TTS) API for Sonna.

Converts text responses into spoken audio.
Supports both free local mode (gTTS) and ElevenLabs (if API key present).
"""
import os
import io
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tts", tags=["tts"])

# Check mode: free (gTTS) or ElevenLabs
USE_ELEVENLABS = bool(os.getenv("ELEVENLABS_API_KEY"))

if USE_ELEVENLABS:
    from elevenlabs import ElevenLabs
    tts_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
else:
    from gtts import gTTS


class TTSRequest(BaseModel):
    text: str
    voice: str | None = "default"  # optional voice ID for ElevenLabs


@router.post("/speak")
async def generate_tts(req: TTSRequest):
    """
    Convert text into audio speech.
    If ELEVENLABS_API_KEY is set, uses ElevenLabs voice.
    Otherwise, defaults to free gTTS (Google Text-to-Speech).
    """
    try:
        if USE_ELEVENLABS:
            logger.info("Using ElevenLabs TTS")
            # Voice defaults to your 'Sonna' voice profile
            audio_stream = tts_client.text_to_speech.convert(
                voice=req.voice or "Sonna",
                model_id="eleven_multilingual_v2",
                text=req.text
            )
            audio_bytes = b"".join(audio_stream)
        else:
            logger.info("Using gTTS (free)")
            tts = gTTS(req.text, lang="en")
            buffer = io.BytesIO()
            tts.write_to_fp(buffer)
            buffer.seek(0)
            audio_bytes = buffer.read()

        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg", headers={"Content-Disposition": "attachment; filename=sonna_output.mp3", "Accept-Ranges": "bytes"},)

    except Exception as e:
        logger.exception("TTS generation failed")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")
