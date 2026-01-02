import asyncio
import uuid
import os
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.models import Document, Scope, Kit, Firm, Client, DocumentStatus

async def seed_knowledge():
    async with AsyncSessionLocal() as db:
        # 1. Get IDs
        firm_result = await db.execute(select(Firm).limit(1))
        firm = firm_result.scalars().first()
        if not firm:
            print("No firm found. Please signup first.")
            return

        client_result = await db.execute(select(Client).where(Client.firm_id == firm.id).limit(1))
        client = client_result.scalars().first()
        
        kit_result = await db.execute(select(Kit).where(Kit.name == "GST").limit(1))
        gst_kit = kit_result.scalars().first()

        print(f"Seeding knowledge for Firm: {firm.name}...")

        # 2. Add sample documents
        samples = [
            {
                "title": "GST Rule 101",
                "scope": Scope.KIT,
                "kit_id": gst_kit.id,
                "text": "GST Rule 101: All taxpayers must file GSTR-1 by the 11th of every month."
            },
            {
                "title": "Firm Onboarding Policy",
                "scope": Scope.FIRM,
                "firm_id": firm.id,
                "text": "Firm Policy: Always collect PAN and Aadhaar during the first client meeting."
            }
        ]
        
        if client:
            samples.append({
                "title": "Client Factsheet",
                "scope": Scope.CLIENT,
                "client_id": client.id,
                "text": f"Client {client.name} uses FIFO for inventory valuation and has a March year-end."
            })

        for s in samples:
            doc = Document(
                title=s["title"],
                scope=s["scope"],
                firm_id=firm.id,
                client_id=s.get("client_id"),
                kit_id=s.get("kit_id"),
                status=DocumentStatus.READY # Skip ingestion for this manual seed
            )
            db.add(doc)
            await db.flush()
            
            # Create a mock embedding record (so RAG can find it)
            # In a real app, this is done via background tasks
            from app.rag.embeddings.base import get_embedder
            embedder = get_embedder()
            embedding_record = {
                "document_id": doc.id,
                "chunk_text": s["text"],
                "chunk_index": 0,
                "embedding": embedder.embed_text(s["text"])
            }
            # We use core SQL because DocEmbedding model might be complex
            from app.models.models import DocEmbedding
            db.add(DocEmbedding(**embedding_record))

        await db.commit()
        print("✅ Sample Knowledge seeded across 3 layers!")

if __name__ == "__main__":
    asyncio.run(seed_knowledge())
