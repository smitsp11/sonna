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
    # start with "small" or "base" to keep it snappy on CPU
    model = WhisperModel("small", compute_type="int8")  # good default on CPU

@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), language: str | None = None):
    allowed = {
        "audio/mp3","audio/wav","audio/mpeg","audio/x-m4a","audio/mp4","audio/webm","audio/m4a"
    }
    if audio.content_type not in allowed:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename).suffix) as tmp:
        data = await audio.read()
        tmp.write(data)
        tmp_path = tmp.name

    try:
        if USE_OPENAI:
            with open(tmp_path, "rb") as f:
                resp = openai_client.audio.transcriptions.create(
                    model="whisper-1",  # OpenAI paid API
                    file=f,
                    language=language
                )
            text = resp.text
        else:
            # Local, free path: faster-whisper
            segments, info = model.transcribe(tmp_path, language=language, vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments)

        return {"text": text}
    except Exception as e:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
