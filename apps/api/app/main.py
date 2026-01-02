from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.api import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set all CORS enabled origins
all_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
# Whitelist production frontend and local dev
all_origins.extend([
    "https://complianceaiexpert.netlify.app",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000"
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=all_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {"status": "ok"}
