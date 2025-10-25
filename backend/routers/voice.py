# backend/routers/voice.py
"""
Voice transcription endpoint for Sonna.

Uses the local Faster-Whisper model for speech-to-text.
No external API calls or OpenAI dependencies required.
"""

import os
import logging
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from faster_whisper import WhisperModel

# Initialize router and logger
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

# Initialize local Whisper model once (recommended model sizes: "tiny", "base", "small", "medium", "large-v3")
# "small" balances speed and accuracy for most use cases
try:
    model = WhisperModel("small", compute_type="int8")
    logger.info("Faster-Whisper model initialized successfully.")
except Exception as e:
    logger.exception("Failed to initialize Whisper model.")
    raise RuntimeError(f"Failed to load Faster-Whisper model: {e}")


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile | str | bytes | None = File(None),
    language: str | None = None
):
    """
    Transcribe audio to text using the local Faster-Whisper model.
    Accepts FastAPI UploadFile or direct bytes/string input.

    Args:
        audio: Audio file (mp3, wav, m4a, etc.)
        language: Optional language code (e.g., "en", "fr", "es")
    Returns:
        dict: {"text": "<transcribed text>"}
    """
    allowed = {
        "audio/mp3", "audio/wav", "audio/mpeg",
        "audio/x-m4a", "audio/mp4", "audio/webm", "audio/m4a"
    }

    tmp_path = None
    try:
        # --- Save input audio to a temp file ---
        if isinstance(audio, UploadFile):
            content_type = audio.content_type
            
            # Flexible audio file type handling
            if content_type and not any(allowed_type in content_type for allowed_type in allowed):
                
                if audio.filename:
                    ext = Path(audio.filename).suffix.lower()
                    if ext in ['.m4a', '.mp3', '.wav', '.mp4', '.webm']:
                        logger.warning(f"Accepting file with type {content_type} based on extension {ext}")
                        content_type = "audio/x-m4a"
                else:
                    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")


            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename).suffix) as tmp:
                data = await audio.read()
                tmp.write(data)
                tmp_path = tmp.name

        elif isinstance(audio, (str, bytes)):
            if isinstance(audio, str) and os.path.exists(audio):
                tmp_path = audio
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp.write(audio if isinstance(audio, bytes) else audio.encode())
                    tmp_path = tmp.name
        else:
            raise HTTPException(status_code=400, detail="No valid audio input provided.")

        # --- Perform transcription ---
        segments, info = model.transcribe(tmp_path, language=language, vad_filter=True)
        text = " ".join(seg.text.strip() for seg in segments)

        return {"text": text}

    except Exception as e:
        logger.exception("Transcription failed.")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                logger.warning(f"Temp file cleanup failed: {tmp_path}")
