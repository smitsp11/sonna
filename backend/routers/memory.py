"""
Memory-related API endpoints for storing and retrieving semantic memories.

This module handles the storage and retrieval of long-term memories
using Pinecone for vector similarity search.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from ..database import get_db
from ..models import Memory, MemoryType, User
from ..services.user_service import get_or_create_default_user
from ..services.pinecone_service import store_memory, search_memories, delete_memory, get_memory_by_id
from ..services.llm_agent import llm_agent

router = APIRouter(prefix="/memories", tags=["memories"])
logger = logging.getLogger(__name__)


class MemoryCreate(BaseModel):
    """Schema for creating a new memory."""
    content: str
    memory_type: MemoryType = MemoryType.FACT
    metadata: Optional[Dict[str, Any]] = None


class MemoryResponse(BaseModel):
    """Schema for memory response."""
    id: int
    content: str
    memory_type: str
    created_at: datetime
    metadata: Dict[str, Any]
    pinecone_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class MemorySearchRequest(BaseModel):
    """Schema for memory search request."""
    query: str
    limit: int = 5
    memory_type: Optional[MemoryType] = None


class MemorySearchResponse(BaseModel):
    """Schema for memory search response."""
    memories: List[Dict[str, Any]]
    total: int


@router.post("/", response_model=MemoryResponse)
async def create_memory(
    memory_data: MemoryCreate,
    db: Session = Depends(get_db)
) -> MemoryResponse:
    """Store a new memory with vector embedding."""
    try:
        user = get_or_create_default_user(db)
        
        # Create memory in database
        memory = Memory(
            user_id=user.id,
            content=memory_data.content,
            memory_type=memory_data.memory_type.value,
            source="manual",
            metadata=memory_data.metadata or {}
        )
        
        db.add(memory)
        db.commit()
        db.refresh(memory)
        
        # Generate embedding
        embedding = await llm_agent.generate_embedding(memory_data.content)
        
        # Store in Pinecone
        pinecone_id = f"mem_{memory.id}"
        metadata = {
            "user_id": user.id,
            "memory_type": memory_data.memory_type.value,
            "created_at": memory.created_at.isoformat(),
            **(memory_data.metadata or {})
        }
        
        success = store_memory(
            memory_id=pinecone_id,
            content=memory_data.content,
            embedding=embedding,
            metadata=metadata
        )
        
        if success:
            memory.pinecone_id = pinecone_id
            db.commit()
        
        logger.info(f"✅ Created memory {memory.id}: {memory_data.content[:50]}...")
        
        return MemoryResponse(
            id=memory.id,
            content=memory.content,
            memory_type=memory.memory_type,
            created_at=memory.created_at,
            metadata=memory.metadata,
            pinecone_id=memory.pinecone_id
        )
        
    except Exception as e:
        logger.error(f"Failed to create memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=MemorySearchResponse)
async def search_memories_semantic(
    query: str,
    limit: int = 5,
    memory_type: Optional[str] = None,
    db: Session = Depends(get_db)
) -> MemorySearchResponse:
    """Search memories using semantic similarity."""
    try:
        user = get_or_create_default_user(db)
        
        # Generate embedding for query
        query_embedding = await llm_agent.generate_embedding(query)
        
        # Prepare filter metadata
        filter_metadata = {"user_id": user.id}
        if memory_type:
            filter_metadata["memory_type"] = memory_type
        
        # Search in Pinecone
        results = search_memories(
            query_embedding=query_embedding,
            limit=limit,
            filter_metadata=filter_metadata
        )
        
        logger.info(f"🔍 Found {len(results)} similar memories for query: {query[:50]}...")
        
        return MemorySearchResponse(
            memories=results,
            total=len(results)
        )
        
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[MemoryResponse])
async def list_memories(
    memory_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
) -> List[MemoryResponse]:
    """List all memories for the current user."""
    try:
        user = get_or_create_default_user(db)
        
        query = db.query(Memory).filter(Memory.user_id == user.id)
        
        if memory_type:
            query = query.filter(Memory.memory_type == memory_type)
        
        memories = query.order_by(Memory.created_at.desc()).limit(limit).all()
        
        return [
            MemoryResponse(
                id=mem.id,
                content=mem.content,
                memory_type=mem.memory_type,
                created_at=mem.created_at,
                metadata=mem.metadata,
                pinecone_id=mem.pinecone_id
            )
            for mem in memories
        ]
        
    except Exception as e:
        logger.error(f"Failed to list memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: int,
    db: Session = Depends(get_db)
) -> MemoryResponse:
    """Get a specific memory by ID."""
    try:
        user = get_or_create_default_user(db)
        
        memory = (
            db.query(Memory)
            .filter(
                Memory.id == memory_id,
                Memory.user_id == user.id
            )
            .first()
        )
        
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        return MemoryResponse(
            id=memory.id,
            content=memory.content,
            memory_type=memory.memory_type,
            created_at=memory.created_at,
            metadata=memory.metadata,
            pinecone_id=memory.pinecone_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{memory_id}")
async def delete_memory_endpoint(
    memory_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """Delete a memory."""
    try:
        user = get_or_create_default_user(db)
        
        memory = (
            db.query(Memory)
            .filter(
                Memory.id == memory_id,
                Memory.user_id == user.id
            )
            .first()
        )
        
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        
        # Delete from Pinecone if it exists there
        if memory.pinecone_id:
            delete_memory(memory.pinecone_id)
        
        # Delete from database
        db.delete(memory)
        db.commit()
        
        logger.info(f"🗑️ Deleted memory {memory_id}")
        
        return {"message": f"Memory {memory_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete memory {memory_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_memory_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get a summary of memories by category."""
    try:
        user = get_or_create_default_user(db)
        
        # Get memory counts by type
        memory_counts = (
            db.query(Memory.memory_type, db.func.count(Memory.id))
            .filter(Memory.user_id == user.id)
            .group_by(Memory.memory_type)
            .all()
        )
        
        # Get recent memories
        recent_memories = (
            db.query(Memory)
            .filter(Memory.user_id == user.id)
            .order_by(Memory.created_at.desc())
            .limit(5)
            .all()
        )
        
        summary = {
            "total_memories": sum(count for _, count in memory_counts),
            "by_type": {mem_type: count for mem_type, count in memory_counts},
            "recent_memories": [
                {
                    "id": mem.id,
                    "content": mem.content[:100] + "..." if len(mem.content) > 100 else mem.content,
                    "type": mem.memory_type,
                    "created_at": mem.created_at.isoformat()
                }
                for mem in recent_memories
            ]
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get memory summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
