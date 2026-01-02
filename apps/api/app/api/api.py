from fastapi import APIRouter

from app.api.endpoints import auth, clients, kits, documents, conversations, services

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(kits.router, prefix="/kits", tags=["kits"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
