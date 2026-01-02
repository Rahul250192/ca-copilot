import os
from uuid import UUID
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.models import Document, DocEmbedding, DocumentStatus
from app.rag.parsers.file_parser import FileParser
from app.rag.chunking.splitter import RecursiveCharacterTextSplitter
from app.rag.embeddings.base import get_embedder

async def ingest_document(document_id: UUID):
    # Create a new session for the background task
    async with AsyncSessionLocal() as db:
        try:
            # Fetch document
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalars().first()
            
            if not document:
                print(f"Document {document_id} not found")
                return

            # Update status to processing
            document.status = DocumentStatus.PROCESSING
            await db.commit()

            # Parse
            parser = FileParser()
            
            from app.services.storage import storage_service
            
            local_path = None
            is_temp = False
            
            # Check if file_path is cloud or local
            # Local paths start with "storage/"
            if not document.file_path.startswith("storage/"):
                # Try to download from cloud
                print(f"Downloading from cloud: {document.file_path}")
                
                # Determine bucket
                from app.models.models import Scope
                is_client_scope = document.scope == Scope.CLIENT or str(document.scope) == "Scope.CLIENT" or str(document.scope) == "CLIENT"
                bucket = "client-context" if is_client_scope else None
                print(f"Bucket selected for download: {bucket} (Scope: {document.scope})")
                
                local_path = storage_service.download_to_temp(document.file_path, bucket=bucket)
                is_temp = True
            else:
                local_path = document.file_path

            if not local_path or not os.path.exists(local_path):
                print(f"File not found: {document.file_path}")
                document.status = DocumentStatus.FAILED
                await db.commit()
                return

            try:
                text = parser.parse(local_path)
            finally:
                # Clean up if it was a temp file
                if is_temp and local_path and os.path.exists(local_path):
                    os.remove(local_path)
            
            if not text:
                print(f"No text extracted for doc {document_id}")
                document.status = DocumentStatus.FAILED
                await db.commit()
                return

            # Chunk
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            chunks = splitter.split_text(text)

            # Embed
            embedder = get_embedder()
            vectors = embedder.embed_batch(chunks)

            # Store Embeddings
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                embedding_entry = DocEmbedding(
                    document_id=document.id,
                    chunk_text=chunk,
                    chunk_index=i,
                    embedding=vector,
                    metadata_={}
                )
                db.add(embedding_entry)

            document.status = DocumentStatus.READY
            await db.commit()
            print(f"Ingestion complete for {document_id}")

        except Exception as e:
            print(f"Ingestion failed for {document_id}: {e}")
            # Try to update status if possible
            try:
                document.status = DocumentStatus.FAILED
                await db.commit()
            except:
                pass
