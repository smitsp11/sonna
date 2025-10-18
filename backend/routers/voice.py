# backend/routers/voice.py
import os
import logging
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, status

USE_OPENAI = os.getenv("USE_OPENAI_WHISPER", "0") == "1"
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

if USE_OPENAI:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    from faster_whisper import WhisperModel
    # model size options: "tiny", "base", "small", "medium", "large-v3"
    model = WhisperModel("small", compute_type="int8")  # local free model

@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile | str | bytes | None = File(None), language: str | None = None):
    """
    Transcribe audio using either local Whisper (default) or OpenAI Whisper (if enabled).
    Accepts both FastAPI UploadFile and direct file-like input from other functions.
    """
    allowed = {
        "audio/mp3","audio/wav","audio/mpeg","audio/x-m4a","audio/mp4","audio/webm","audio/m4a"
    }

    # Handle both UploadFile and file-like input gracefully
    tmp_path = None
    try:
        if isinstance(audio, UploadFile):
            content_type = audio.content_type
            if content_type not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}"
                )
            # Write UploadFile to temp
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename).suffix) as tmp:
                data = await audio.read()
                tmp.write(data)
                tmp_path = tmp.name

        elif isinstance(audio, (str, bytes)):  
            # if already file path or bytes
            if isinstance(audio, str) and os.path.exists(audio):
                tmp_path = audio
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp.write(audio if isinstance(audio, bytes) else audio.encode())
                    tmp_path = tmp.name
        else:
            raise HTTPException(status_code=400, detail="No valid audio input provided")

        # --- Transcription ---
        if USE_OPENAI:
            with open(tmp_path, "rb") as f:
                resp = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language
                )
            text = resp.text
        else:
            segments, info = model.transcribe(tmp_path, language=language, vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments)

        return {"text": text}

    except Exception as e:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                logger.warning(f"Temp file cleanup failed: {tmp_path}")