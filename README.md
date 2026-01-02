# CA-Copilot Backend

A production-ready, client-scoped RAG backend for CA specialists.

## Features
- **3 Decision Layers**: Retrieval from Firm Knowledge, Topic Kits, and Client Context.
- **Strict Isolation**: Row-level security logic ensuring zero data leakage between firms or clients.
- **Specialist Knowledge**: Priority-based RAG that favors "Kits" (GST, Tax, ROC, etc.).
- **Auto-Deployment**: Zero-config setup with automated migrations and data seeding.

## Tech Stack
- **Backend**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL + `pgvector`
- **ORM**: SQLAlchemy (Async) + Alembic
- **Auth**: JWT (JSON Web Tokens)

---

## Quick Start (Zero-Config)

### 1. Requirements
- Docker & Docker Compose
- `openssl` (for random secret generation)

### 2. Deploy
Run the automated deployment script:
```bash
./deploy.sh
```
This will:
- Generate a secure `.env` file.
- Start the DB and API.
- Create all tables and enable `pgvector`.
- Seed default Knowledge Kits (GST, Income Tax, Audit, ROC).

---

## API Usage Examples

### 1. Signup & Login
```bash
# Signup
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@firm.com", "password": "password123", "full_name": "Firm Owner"}'

# Login (Returns JWT)
curl -X POST http://localhost:8000/auth/login \
  -d "username=owner@firm.com&password=password123"
```

### 2. Management (Clients & Kits)
```bash
# Create Client
curl -X POST http://localhost:8000/api/v1/clients/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Reliance Industries"}'

# List All Clients
curl -X GET http://localhost:8000/api/v1/clients/ \
  -H "Authorization: Bearer <TOKEN>"

# Attach Kit to Conversation
curl -X PUT http://localhost:8000/conversations/<CONV_ID>/kits \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '["<KIT_ID_FOR_GST>"]'
```

### 3. Document Ingestion
```bash
# Upload Client Document
curl -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer <TOKEN>" \
  -F "title=Tax Audit 2023" \
  -F "scope=CLIENT" \
  -F "client_id=<CLIENT_ID>" \
  -F "file=@audit_report.pdf"
```

### 4. Specialized Chat (RAG)
```bash
curl -X POST http://localhost:8000/conversations/<CONV_ID>/chat \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"content": "How should we handle current GST return?"}'
```
*Note: The response will include citations grouped by scope (KIT, FIRM, or CLIENT).*

---

## Testing
Run unit tests for scope security:
```bash
docker-compose run api pytest apps/api/tests/test_compliance.py
```

## Folder Structure
```text
ca-copilot-backend/
├── apps/
│   └── api/
│       ├── app/ (Core Logic)
│       ├── migrations/
│       ├── scripts/ (Start & Seed)
│       └── tests/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
└── README.md
```