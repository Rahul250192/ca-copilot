# CA-Copilot API Reference

This document provides detailed information about every API endpoint in the CA-Copilot system.

**Base URL**: `http://localhost:8000/api/v1`  
**Authentication**: All endpoints (except login/signup) require a JWT Bearer Token:  
> [!TIP]
> **Supabase Connection Strings**: You can paste your Supabase URI exactly as it is (starting with `postgres://`). The backend will automatically fix the protocol and add the `+asyncpg` driver for you.

## 🔐 Authentication

### `POST /auth/signup`
Creates a new Firm and an Owner-level user.
- **Request Body**:
  ```json
  {
    "email": "user@firm.com",
    "password": "secure_password",
    "full_name": "John Doe",  // Optional
    "firm_name": "Doe Accounting Associates"
  }
  ```

### `POST /auth/login`
Exchanges credentials for a JWT token.
- **Request Body** (Form Data): `username`, `password`
- **Response**: `{ "access_token": "...", "token_type": "bearer" }`

### `GET /auth/me`
Returns the current user profile.

---

## 🏢 Client Management

### `GET /clients/`
Lists all clients for the firm.
- **Note**: Deeply loads associated **Services** and their **Knowledge Kits**.

### `POST /clients/`
Creates a new client.
- **Request Body**: 
  ```json
  { 
    "name": "Client Name",
    "gst_number": "27AAACR1234A1Z1", // Optional
    "service_ids": ["uuid-1", "uuid-2"] // Optional
  }
  ```

### `GET /clients/{client_id}`
Retrieves a specific client's data.

### `PUT /clients/{client_id}/services`
Associates services with a client.
- **Request Body**: `["uuid-1", "uuid-2"]` (Array of Service IDs)

---

## 🛠 Service Layer

### `GET /services/`
Lists all services created by the firm.

### `POST /services/`
Creates a new service bundle.
- **Request Body**:
  ```json
  {
    "name": "Full GST Service",
    "description": "...",
    "kit_ids": ["uuid-gst-kit"]
  }
  ```

### `PUT /services/{id}/kits`
Updates the Knowledge Kits bundled within a service.
- **Request Body**: `["uuid-kit-1", "uuid-kit-2"]`

---

## 📦 Topic Kits (Specialist Knowledge)

### `GET /kits/`
Lists all specialized knowledge packs (GST, Income Tax, Audit, ROC).

### `POST /kits/`
Creates a new Topic Kit (Owner/Admin only).
- **Request Body**: `{ "name": "GST", "description": "..." }`

---

## 💬 Conversations & AI Chat

### `POST /conversations/`
Starts a new conversation.
- **Request Body**:
  ```json
  {
    "title": "Monthly Consultation",
    "client_id": "uuid-client",
    "service_id": "uuid-service"
  }
  ```
> [!TIP]
> Providing a `service_id` will **automatically attach** all relevant Knowledge Kits to the conversation.

### `GET /conversations?client_id={uuid}`
Lists all conversations for a specific client.

### `POST /conversations/{id}/chat`
**Core RAG Endpoint**. Sends a message and generates an AI response with citations.
- **Request Body**: `{ "content": "Query text" }`
- **Response**:
  ```json
  {
    "role": "assistant",
    "content": "[HIGH CONFIDENCE] ...",
    "citations": [ { "scope": "KIT", "chunk_text": "...", "score": 0.0 } ]
  }
  ```

---

## 📄 Document Management

### `POST /documents/upload`
Uploads and ingests a file into the RAG system.
- **Multi-part Form**:
  - `file`: (Binary PDF/Excel)
  - `title`: "Document Title"
  - `scope`: "FIRM" | "KIT" | "CLIENT"
  - `client_id` / `kit_id`: (Optional based on scope)

### `GET /documents/`
Lists all documents.
- **Status**: `uploaded` | `processing` | `ready` | `failed`
