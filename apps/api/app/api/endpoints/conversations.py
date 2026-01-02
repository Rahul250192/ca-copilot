from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, delete, insert
from sqlalchemy.orm import selectinload

from app.api import deps
from app.db.session import AsyncSessionLocal
from app.models.models import Conversation, Message, MessageRole, Kit, conversation_kits, RetrievalLog, Scope, Service
from app.schemas import conversation as conv_schemas
from app.schemas import message as msg_schemas
from app.rag.retrieval import Retriever

router = APIRouter()

@router.post("/", response_model=conv_schemas.ConversationInDBBase)
async def create_conversation(
    *,
    db: AsyncSession = Depends(deps.get_db),
    conv_in: conv_schemas.ConversationCreate,
    current_user: Any = Depends(deps.get_current_user),
) -> Any:
    conv = Conversation(
        title=conv_in.title,
        client_id=conv_in.client_id,
        firm_id=current_user.firm_id
    )
    
    if conv_in.service_id:
        stmt = select(Service).options(selectinload(Service.kits)).where(
            Service.id == conv_in.service_id,
            Service.firm_id == current_user.firm_id
        )
        result = await db.execute(stmt)
        service = result.scalars().first()
        if service:
            conv.attached_kits = service.kits

    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv

@router.post("/{conv_id}/chat", response_model=msg_schemas.Message)
async def chat(
    conv_id: UUID,
    message_in: msg_schemas.MessageCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_current_user),
) -> Any:
    # Load conversation with attached kits
    stmt = select(Conversation).options(selectinload(Conversation.attached_kits)).where(Conversation.id == conv_id)
    result = await db.execute(stmt)
    conv = result.scalars().first()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.firm_id != current_user.firm_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Save User Message
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=message_in.content
    )
    db.add(user_msg)
    await db.commit()
    
    # Retrieve Context
    retriever = Retriever(db)
    kit_ids = [k.id for k in conv.attached_kits]
    
    docs = await retriever.retrieve(
        query=message_in.content,
        firm_id=conv.firm_id,
        client_id=conv.client_id,
        kit_ids=kit_ids
    )
    
    # Build Context and Prompts
    from app.services.prompt import PromptService
    from app.services.llm import LLMService
    kit_names = [k.name for k in conv.attached_kits]
    system_prompt = PromptService.build_specialist_system_prompt(kit_names)
    formatted_context = PromptService.format_context_for_prompt(docs)
    
    # Generate AI response
    answer_text = await LLMService.generate_response(
        system_prompt=system_prompt,
        user_message=formatted_context + "\n\nUser Question: " + message_in.content
    )
    
    # Build citations from already loaded docs
    citations = []
    for d in docs:
        citations.append(
            msg_schemas.Citation(
                document_id=d.document_id,
                scope=d.document.scope.value,
                chunk_text=d.chunk_text[:200] + "...",
                chunk_index=d.chunk_index,
                score=0.0
            )
        )
    
    # Save Assistant Message
    assist_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=answer_text
    )
    db.add(assist_msg)
    await db.flush()
    
    # Save Retrieval Logs
    retrieval_log = RetrievalLog(
        message_id=assist_msg.id,
        cited_chunks=[
            {
                "document_id": str(d.document_id),
                "scope": d.document.scope.value,
                "document_title": d.document.title,
                "chunk_index": d.chunk_index,
                "text_preview": d.chunk_text[:100]
            } for d in docs
        ]
    )
    db.add(retrieval_log)
    
    await db.commit()
    await db.refresh(assist_msg)
    
    resp = msg_schemas.Message.model_validate(assist_msg)
    resp.citations = citations
    return resp

@router.get("/conversations", response_model=List[conv_schemas.ConversationInDBBase])
async def read_client_conversations(
    client_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_current_user),
) -> Any:
    query = select(Conversation).where(
        Conversation.client_id == client_id,
        Conversation.firm_id == current_user.firm_id
    )
    result = await db.execute(query)
    return result.scalars().all()

@router.put("/{conv_id}/kits")
async def attach_kits(
    conv_id: UUID,
    kit_ids: List[UUID],
    db: AsyncSession = Depends(deps.get_db),
    current_user: Any = Depends(deps.get_current_user),
):
    """
    Attach topic kits to a conversation.
    """
    # 1. Fetch conversation with kits loaded
    stmt = select(Conversation).options(selectinload(Conversation.attached_kits)).where(
        Conversation.id == conv_id,
        Conversation.firm_id == current_user.firm_id
    )
    result = await db.execute(stmt)
    conv = result.scalars().first()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # 2. Fetch kits
    if kit_ids:
        kit_stmt = select(Kit).where(Kit.id.in_(kit_ids))
        kit_result = await db.execute(kit_stmt)
        conv.attached_kits = kit_result.scalars().all()
    else:
        conv.attached_kits = []
    
    await db.commit()
    return {"status": "ok"}
