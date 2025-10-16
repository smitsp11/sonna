'''
Voice-related API endpoints for handling voice input/output operations.

This module contains routes for processing voice commands, streaming audio,
and managing voice interactions with the assistant.
'''
import os
import logging
import tempfile
from pathlib import Path
from typing import Optional, Annotated
from fastapi import APIRouter, UploadFile, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Response model
class TranscriptionResponse(BaseModel):
    text: str

router = APIRouter()

@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Transcribe audio to text",
    description="""Transcribes the provided audio file to text using OpenAI's Whisper API.
    Supported formats: mp3, wav, m4a, webm, mp4, mpga, m4a, wav, mpeg.
    Maximum file size: 25MB."""
)
async def transcribe_audio(
    audio: UploadFile,
    language: Annotated[Optional[str], "Optional language code (e.g., 'en', 'es')"] = None
) -> TranscriptionResponse:
    '''
    Transcribe voice input to text using OpenAI's Whisper API.
    
    Args:
        audio: Audio file containing voice input
        language: Optional ISO-639-1 language code (e.g., 'en', 'es')
        
    Returns:
        TranscriptionResponse: Contains the transcribed text
        
    Raises:
        HTTPException: If file type is unsupported or transcription fails
    '''
    # Validate file type
    allowed_types = {
        'audio/mp3', 'audio/wav', 'audio/m4a', 'audio/webm',
        'audio/mp4', 'audio/mpeg', 'audio/x-m4a'
    }
    
    if audio.content_type not in allowed_types:
        logger.warning(f"Unsupported file type: {audio.content_type}")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename).suffix) as temp_audio:
        try:
            # Save uploaded file to temp location
            contents = await audio.read()
            temp_audio.write(contents)
            temp_audio_path = temp_audio.name
            
            logger.info(f"Processing audio file: {audio.filename} ({len(contents)} bytes)")
            
            # Transcribe using Whisper API
            with open(temp_audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language
                )
                
            transcription = response.text
            logger.info("Transcription successful")
            
            return TranscriptionResponse(text=transcription)
            
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transcription failed: {str(e)}"
            )
            
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_audio_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_audio_path}: {e}")

@router.post("/process-command")
async def process_command(text: str) -> dict:
    '''
    Process transcribed text command through the LLM agent.
    
    Args:
        text: Transcribed text from voice input
        
    Returns:
        dict: Processed response from the assistant
    '''
    # TODO: Implement actual command processing
    return {"response": "I'll help you with that", "action": "respond"}