from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_
from app.models.models import DocEmbedding, Document, Scope
from app.rag.embeddings.base import get_embedder

class Retriever:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedder = get_embedder()

    async def retrieve(
        self,
        query: str,
        firm_id: UUID,
        client_id: UUID,
        kit_ids: List[UUID],
        limit: int = 5
    ) -> List[DocEmbedding]:
        query_vector = self.embedder.embed_text(query)
        
        # Build filter conditions
        # We need to join Document to check scope constraints
        # but pgvector usually works on the embedding table.
        # We can do a join.
        
        # Conditions:
        # 1. Document belongs to firm_id (if scope=FIRM or scope=CLIENT or scope=KIT? No, KIT might be global).
        # Check Scope logic again:
        # FIRM scope: firm_id match
        # CLIENT scope: client_id match
        # KIT scope: kit_id in kit_ids
        
        # If Kit is global, it might not have firm_id set. 
        # But if Kit is firm specific, it has firm_id.
        # Let's assume Kits are accessible if in kit_ids list, regardless of firm_id on the document itself
        # (assuming the association to conversation implies access).
        
        conditions = [
            and_(Document.scope == Scope.CLIENT, Document.client_id == client_id),
            and_(Document.scope == Scope.FIRM, Document.firm_id == firm_id),
        ]
        
        if kit_ids:
            conditions.append(and_(Document.scope == Scope.KIT, Document.kit_id.in_(kit_ids)))
            
        where_clause = or_(*conditions)
        
        # Perform vector search
        # Using l2_distance or cosine_distance
        # Format: select(DocEmbedding).join(Document).filter(where_clause).order_by(DocEmbedding.embedding.l2_distance(query_vector)).limit(limit)
        
        stmt = (
            select(DocEmbedding)
            .join(Document)
            .options(selectinload(DocEmbedding.document))
            .where(where_clause)
            .order_by(DocEmbedding.embedding.l2_distance(query_vector))
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        hits = result.scalars().all()
        
        print(f"🔍 RAG: Found {len(hits)} relevant chunks for query: '{query[:50]}...'", flush=True)
            
        return hits
