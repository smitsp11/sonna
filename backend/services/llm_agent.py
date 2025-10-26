"""
LLM Agent service for handling natural language understanding and generation.

This module provides an interface to interact with language models
for processing user inputs and generating appropriate responses.
Current implementation uses Google Gemini for reasoning
and placeholder embeddings until vector API integration.
"""

from typing import Dict, Any, Optional
import logging
import httpx
import google.generativeai as genai
from ..config import settings

logger = logging.getLogger(__name__)


class LLMAgent:
    """Service for handling interactions with large language models."""

    def __init__(self, model_name: str = "gemini-pro"):
        """
        Initialize the LLM agent.

        Args:
            model_name: Name of the Gemini model to use.
        """
        self.model_name = model_name
        self.api_key = settings.GEMINI_API_KEY
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        
        # Configure genai with API key if available
        if self.api_key:
            genai.configure(api_key=self.api_key)
            logger.info(f"✅ Initialized Gemini LLM agent with model: {model_name}")
        else:
            logger.warning("⚠️ GEMINI_API_KEY not set in settings")

    async def process_input(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process user input and return an AI-generated response.

        Args:
            user_input: The user's text input
            context: Additional context for the conversation

        Returns:
            Dict containing the response text and any actions
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set; returning fallback response.")
            return {
                "text": f"[Gemini unavailable] I received your input: {user_input}",
                "actions": [],
                "context": context or {},
            }

        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}
        payload = {"contents": [{"parts": [{"text": user_input}]}]}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.api_url, headers=headers, params=params, json=payload)
                response.raise_for_status()
                data = response.json()

            model_reply = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            return {
                "text": model_reply or "I'm here, but I couldn't generate a response.",
                "actions": [],
                "context": context or {},
            }

        except Exception as e:
            logger.exception("Gemini API call failed.")
            return {
                "text": f"[Error] Gemini failed to respond: {e}",
                "actions": [],
                "context": context or {},
            }

    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate a vector embedding for the given text using Gemini.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set; returning placeholder embedding.")
            return [0.0] * 768  # placeholder embedding
        
        try:
            # Use Gemini's embedding model
            result = genai.embed_content(
                model="models/embedding-001",
                content=text,
                task_type="retrieval_document"
            )
            
            embedding = result['embedding']
            logger.debug(f"Generated embedding of length {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # Return placeholder embedding on failure
            return [0.0] * 768


# Singleton instance for reuse across app
llm_agent = LLMAgent()
