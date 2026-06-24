from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
from typing import List
import json

from services.pdf_processor import PDFProcessor
from services.vector_store import VectorStore
from services.chat_service import ChatService
from models.schemas import ChatRequest, ChatResponse, DocumentInfo

app = FastAPI(title="PDF Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pdf_processor = PDFProcessor()
vector_store = VectorStore()
chat_service = ChatService(vector_store)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


@app.post("/upload")
async def upload_pdfs(files: List[UploadFile] = File(...)):
    """Upload and process PDF files."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} is not a PDF"
            )

        content = await file.read()
        if len(content) > 50 * 1024 * 1024:  # 50 MB
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds 50 MB limit"
            )

        try:
            doc_id, chunks_count, page_count = await pdf_processor.process(
                content, file.filename, vector_store
            )
            results.append({
                "doc_id": doc_id,
                "filename": file.filename,
                "chunks": chunks_count,
                "pages": page_count,
                "status": "success"
            })
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e)
            })

    return {"documents": results}


@app.get("/documents")
async def list_documents():
    """List all uploaded documents."""
    docs = vector_store.list_documents()
    return {"documents": docs}


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its chunks."""
    success = vector_store.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "doc_id": doc_id}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat responses with source attribution."""

    async def generate():
        async for chunk in chat_service.stream_response(
            question=request.question,
            conversation_history=request.conversation_history,
            doc_ids=request.doc_ids
        ):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint."""
    response = await chat_service.get_response(
        question=request.question,
        conversation_history=request.conversation_history,
        doc_ids=request.doc_ids
    )
    return response


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
