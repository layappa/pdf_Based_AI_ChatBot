from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class Source(BaseModel):
    doc_id: str
    filename: str
    page: int
    excerpt: str
    score: float


class ChatRequest(BaseModel):
    question: str
    conversation_history: List[Message] = []
    doc_ids: Optional[List[str]] = None  # None = search all docs


class ChatResponse(BaseModel):
    answer: str
    sources: List[Source]
    conversation_history: List[Message]


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunks: int
    pages: int
