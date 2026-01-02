import time
from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
import uuid

app = FastAPI(title="CA-Copilot Mock Backend")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock Data Storage
USERS = []
CLIENTS = [
    {
        "id": "c1", 
        "name": "Apple Inc.", 
        "gstins": ["27AAACA1234A1Z1"], 
        "pan": "AAACA1234A",
        "cin": "L01234KA2024PLC000001",
        "tan": "MUMW12345A",
        "iec": "0123456789",
        "services": []
    },
    {
        "id": "c2", 
        "name": "Google LLC", 
        "gstins": ["27AAACG5678G1Z2"], 
        "pan": "AAACG5678G",
        "cin": "L56789KA2024PLC000002",
        "tan": "MUMW56789B",
        "iec": "9876543210",
        "services": []
    }
]
CONVERSATIONS = {}

# Pydantic Models
class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str
    firm_name: str

class ClientCreate(BaseModel):
    name: str
    gstins: List[str] = []
    pan: Optional[str] = None
    cin: Optional[str] = None
    tan: Optional[str] = None
    iec: Optional[str] = None

class ChatRequest(BaseModel):
    content: str

class ConversationCreate(BaseModel):
    title: str
    client_id: str
    service_id: Optional[str] = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/auth/signup")
def signup(user: UserCreate):
    USERS.append(user.dict())
    return {"message": "User created successfully"}

@app.post("/api/v1/auth/login")
def login(username: str = Form(...), password: str = Form(...)):
    # Simple mock check
    return {
        "access_token": "mock_token_" + str(uuid.uuid4()),
        "token_type": "bearer"
    }

@app.get("/api/v1/auth/me")
def get_me():
    return {
        "full_name": "Demo User",
        "email": "demo@example.com",
        "firm_name": "Compliance Experts"
    }

@app.get("/api/v1/clients/")
def list_clients():
    return CLIENTS

@app.post("/api/v1/clients/")
def create_client(client: ClientCreate):
    new_client = {
        "id": str(uuid.uuid4()),
        "name": client.name,
        "gstins": client.gstins,
        "pan": client.pan,
        "cin": client.cin,
        "tan": client.tan,
        "iec": client.iec,
        "services": []
    }
    CLIENTS.append(new_client)
    return new_client

@app.get("/api/v1/clients/{client_id}")
def get_client(client_id: str):
    for c in CLIENTS:
        if c["id"] == client_id:
            return c
    raise HTTPException(status_code=404, detail="Client not found")

@app.post("/api/v1/conversations/")
def create_conversation(conv: ConversationCreate):
    conv_id = str(uuid.uuid4())
    CONVERSATIONS[conv_id] = []
    return {"id": conv_id, "title": conv.title}

@app.post("/api/v1/conversations/{id}/chat")
def chat(id: str, req: ChatRequest):
    time.sleep(1) # Simulate thinking
    return {
        "role": "assistant",
        "content": f"Based on the documents for this client, I can confirm that {req.content}. In compliance with GST rules, this requires proper filing of Statement 3.",
        "citations": [
            {"chunk_text": "GST Circular 125/44/2019 specifies the refund process for zero-rated supplies.", "score": 0.95}
        ]
    }

@app.post("/api/v1/documents/upload")
async def upload_document(file: UploadFile = File(...), title: str = Form(...), scope: str = Form(...)):
    return {"status": "success", "id": str(uuid.uuid4()), "message": f"Document '{title}' uploaded and ingested."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
