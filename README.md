# DocChat — PDF AI Chatbot

Ask questions about your PDF documents using an AI-powered chatbot with semantic search and source attribution.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Browser (React)                      │
│   ┌──────────┐    ┌───────────────────────────────────┐ │
│   │ Sidebar  │    │         Chat Area                 │ │
│   │  - Upload│    │  - Streaming responses            │ │
│   │  - Docs  │    │  - Source cards with excerpts     │ │
│   └──────────┘    └───────────────────────────────────┘ │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP / SSE
┌───────────────────────────▼─────────────────────────────┐
│                  FastAPI Backend                         │
│                                                          │
│  POST /upload ──► PDF Processor ──► Chunker             │
│                                         │               │
│  POST /chat/stream                      ▼               │
│       │                          ChromaDB               │
│       ▼                      (vector store)             │
│  Hybrid Search ◄────────────────────────┤               │
│       │                                 │               │
│       ▼                          Embeddings             │
│  OpenRouter ◄──── Context ◄──── (MiniLM-L6-v2)         │
│       │                                                  │
│       ▼                                                  │
│  SSE Stream ──► browser                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### Chunking Strategy
- **Paragraph-aware splitting** with a 500-token target size and 100-token overlap
- Paragraph boundaries are preferred split points over arbitrary token cuts
- Very long paragraphs are further split at sentence boundaries
- Page numbers are preserved in metadata for source attribution
- Overlap ensures context at chunk boundaries isn't lost

### Embedding Model
**`all-MiniLM-L6-v2`** (sentence-transformers)
- 384-dimensional embeddings, 80MB model size
- Runs locally — no per-embedding API costs
- 5× faster than larger models with ~95% of the quality for document QA
- Good balance between speed and accuracy for general English documents

### Retrieval Approach
**Hybrid Search** (70% semantic + 30% BM25)
- Semantic search via ChromaDB cosine similarity finds conceptually related chunks
- BM25 keyword scoring boosts chunks containing exact query terms
- Top-5 chunks with minimum 0.15 cosine similarity threshold
- Deduplication prevents the same page excerpt appearing multiple times

### Prompt Design
- System prompt enforces strict grounding: answers must come only from the provided context
- Context is formatted with numbered source labels matching the source cards shown in UI
- Conversation history (last 10 turns) is included for follow-up questions
- Fallback message when no relevant content is found (avoids hallucination)

---

## Setup Instructions

### Option A: Local Development (Recommended for first run)

**Prerequisites:** Python 3.9+, Node.js 18+

1. **Clone and configure:**
   ```bash
   git clone <your-repo-url>
   cd pdf-chatbot
   ```

2. **Backend setup:**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env — set OPENROUTER_API_KE (free at https://openrouter.ai/)
   pip install -r requirements.txt
   python start.py
   # Backend runs at http://localhost:8000
   ```

3. **Frontend setup (new terminal):**
   ```bash
   cd frontend
   npm install
   npm start
   # Frontend runs at http://localhost:3000
   ```

4. Open **http://localhost:3000** in your browser.

---

### Option B: Docker Compose

**Prerequisites:** Docker, Docker Compose

1. **Configure environment:**
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your OPENROUTER_API_KE
   ```

2. **Build and run:**
   ```bash
   docker-compose up --build
   ```

3. Open **http://localhost:3000** — frontend proxies API calls to backend.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KE` | ✅ Yes | — | Free key from https://openrouter.ai/ |
| `OPENROUTER_MODELS` | No | `openrouter/free` |
| `EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `CHROMA_PERSIST_DIR` | No | `./chroma_data` | ChromaDB storage path |

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/upload` | POST | Upload PDF files (multipart/form-data) |
| `/documents` | GET | List all documents |
| `/documents/{id}` | DELETE | Delete a document |
| `/chat/stream` | POST | Streaming chat (SSE) |
| `/chat` | POST | Non-streaming chat |

---

## Features
- ✅ Upload multiple PDFs (up to 50 MB each)
- ✅ Semantic + BM25 hybrid search
- ✅ Streaming responses via SSE
- ✅ Source attribution with page numbers and excerpts
- ✅ Relevance scores on sources
- ✅ Conversation history (last 10 turns)
- ✅ Select specific documents to search
- ✅ Docker setup
- ✅ Persistent vector store (ChromaDB)
