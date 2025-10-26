"""
Pinecone vector database service for semantic memory storage.

This module handles all interactions with Pinecone for storing
and retrieving semantic memories using vector similarity search.
"""

import logging
from typing import List, Dict, Any, Optional
import pinecone
from pinecone import Pinecone, ServerlessSpec
from ..config import settings

logger = logging.getLogger(__name__)

# Initialize Pinecone client
try:
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    PINECONE_ENABLED = True
    logger.info("✅ Pinecone client initialized successfully")
except Exception as e:
    PINECONE_ENABLED = False
    logger.error(f"❌ Failed to initialize Pinecone client: {e}")

# Index configuration
INDEX_NAME = settings.PINECONE_INDEX_NAME
DIMENSION = 768  # Gemini embedding dimension


def get_or_create_index():
    """
    Get existing index or create a new one if it doesn't exist.
    
    Returns:
        Pinecone index object
    """
    if not PINECONE_ENABLED:
        raise RuntimeError("Pinecone client not initialized")
    
    try:
        # Check if index exists
        if INDEX_NAME in pc.list_indexes().names():
            logger.info(f"📦 Using existing Pinecone index: {INDEX_NAME}")
            return pc.Index(INDEX_NAME)
        else:
            # Create new index
            logger.info(f"🔨 Creating new Pinecone index: {INDEX_NAME}")
            pc.create_index(
                name=INDEX_NAME,
                dimension=DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            logger.info(f"✅ Created Pinecone index: {INDEX_NAME}")
            return pc.Index(INDEX_NAME)
            
    except Exception as e:
        logger.error(f"Failed to get/create Pinecone index: {e}")
        raise


def store_memory(memory_id: str, content: str, embedding: List[float], metadata: Dict[str, Any]) -> bool:
    """
    Store a memory in Pinecone with its embedding.
    
    Args:
        memory_id: Unique identifier for the memory
        content: Text content of the memory
        embedding: Vector embedding of the content
        metadata: Additional metadata to store
        
    Returns:
        True if successful, False otherwise
    """
    if not PINECONE_ENABLED:
        logger.warning("Pinecone not enabled, skipping memory storage")
        return False
    
    try:
        index = get_or_create_index()
        
        # Prepare vector for storage
        vector_data = {
            "id": memory_id,
            "values": embedding,
            "metadata": {
                "content": content,
                **metadata
            }
        }
        
        # Upsert the vector
        index.upsert(vectors=[vector_data])
        logger.info(f"✅ Stored memory {memory_id} in Pinecone")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store memory {memory_id} in Pinecone: {e}")
        return False


def search_memories(query_embedding: List[float], limit: int = 5, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Search for similar memories using vector similarity.
    
    Args:
        query_embedding: Query vector to search for
        limit: Maximum number of results to return
        filter_metadata: Optional metadata filters
        
    Returns:
        List of similar memories with scores
    """
    if not PINECONE_ENABLED:
        logger.warning("Pinecone not enabled, returning empty results")
        return []
    
    try:
        index = get_or_create_index()
        
        # Perform vector search
        search_results = index.query(
            vector=query_embedding,
            top_k=limit,
            include_metadata=True,
            filter=filter_metadata
        )
        
        # Format results
        memories = []
        for match in search_results.matches:
            memories.append({
                "id": match.id,
                "score": match.score,
                "content": match.metadata.get("content", ""),
                "metadata": {k: v for k, v in match.metadata.items() if k != "content"}
            })
        
        logger.info(f"🔍 Found {len(memories)} similar memories")
        return memories
        
    except Exception as e:
        logger.error(f"Failed to search memories in Pinecone: {e}")
        return []


def delete_memory(memory_id: str) -> bool:
    """
    Delete a memory from Pinecone.
    
    Args:
        memory_id: ID of the memory to delete
        
    Returns:
        True if successful, False otherwise
    """
    if not PINECONE_ENABLED:
        logger.warning("Pinecone not enabled, skipping memory deletion")
        return False
    
    try:
        index = get_or_create_index()
        index.delete(ids=[memory_id])
        logger.info(f"🗑️ Deleted memory {memory_id} from Pinecone")
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id} from Pinecone: {e}")
        return False


def get_memory_by_id(memory_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific memory by its ID.
    
    Args:
        memory_id: ID of the memory to retrieve
        
    Returns:
        Memory data if found, None otherwise
    """
    if not PINECONE_ENABLED:
        logger.warning("Pinecone not enabled, cannot retrieve memory")
        return None
    
    try:
        index = get_or_create_index()
        
        # Fetch the vector
        fetch_result = index.fetch(ids=[memory_id])
        
        if memory_id in fetch_result.vectors:
            vector_data = fetch_result.vectors[memory_id]
            return {
                "id": memory_id,
                "content": vector_data.metadata.get("content", ""),
                "metadata": {k: v for k, v in vector_data.metadata.items() if k != "content"}
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to retrieve memory {memory_id} from Pinecone: {e}")
        return None


def get_index_stats() -> Dict[str, Any]:
    """
    Get statistics about the Pinecone index.
    
    Returns:
        Dictionary with index statistics
    """
    if not PINECONE_ENABLED:
        return {"error": "Pinecone not enabled"}
    
    try:
        index = get_or_create_index()
        stats = index.describe_index_stats()
        return {
            "total_vector_count": stats.total_vector_count,
            "dimension": stats.dimension,
            "index_fullness": stats.index_fullness
        }
        
    except Exception as e:
        logger.error(f"Failed to get Pinecone index stats: {e}")
        return {"error": str(e)}


def health_check() -> bool:
    """
    Check if Pinecone service is healthy and accessible.
    
    Returns:
        True if healthy, False otherwise
    """
    if not PINECONE_ENABLED:
        return False
    
    try:
        # Try to get index stats as a health check
        stats = get_index_stats()
        return "error" not in stats
        
    except Exception as e:
        logger.error(f"Pinecone health check failed: {e}")
        return False
