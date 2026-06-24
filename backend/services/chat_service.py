import os
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from openai import AsyncOpenAI

from models.schemas import ChatResponse, Source, Message
from services.vector_store import VectorStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise document analysis assistant. Your job is to answer questions based strictly on the provided document excerpts.

RULES:
1. Answer ONLY based on the provided context. Do not use outside knowledge.
2. If the answer is not in the context, say "I couldn't find information about that in the uploaded documents."
3. Always be specific — cite the exact content from the excerpts.
4. Keep answers concise and well-structured.
5. If information appears on multiple pages, synthesize it clearly.
6. For factual questions, quote directly from the source when helpful.

FORMAT:
- Use markdown for structure when appropriate (bullet points, bold key terms)
- Keep responses focused and avoid unnecessary padding
- End complex answers with a brief summary if helpful"""


class ChatService:
    """
    Orchestrates RAG pipeline: retrieve relevant chunks, build prompt, call OpenRouter with smart fallback routing.
    """

    TOP_K = 5
    MIN_SCORE = 0.15

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")
        
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        # Read the list of reliable free models from .env
        # Read the list from .env, fallback to a guaranteed active model if .env is missing
        # Read the list of reliable free models from .env
        models_env = os.environ.get("OPENROUTER_MODELS", "openrouter/free")
        self.models_list = [m.strip(' "\'') for m in models_env.split(",")]
        
        logger.info(f"OpenRouter routing pool initialized: {self.models_list}")

    def _retrieve_context(self, question: str, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        results = self.vector_store.hybrid_search(
            query=question,
            n_results=self.TOP_K,
            doc_ids=doc_ids,
        )
        if doc_ids:
            return results
        return [r for r in results if r["score"] >= self.MIN_SCORE]

    def _build_context_block(self, chunks: List[Dict[str, Any]]) -> str:
        if not chunks:
            return "No relevant document content found."
        parts = []
        for i, chunk in enumerate(chunks, 1):
            pages_str = ", ".join(str(p) for p in chunk["pages"])
            parts.append(f"[Source {i}: {chunk['filename']}, Page(s) {pages_str}]\n{chunk['text']}")
        return "\n\n---\n\n".join(parts)

    def _build_messages(self, conversation_history: List[Message], question: str, context: str) -> List[Dict]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        recent = conversation_history[-10:]
        for msg in recent:
            if msg.role in ["user", "assistant"]:
                messages.append({"role": msg.role, "content": msg.content})
                
        user_msg = (
            "Here are the relevant excerpts from the uploaded documents:\n\n"
            f"{context}\n\n---\n\n"
            f"Based on the above excerpts, please answer this question:\n{question}"
        )
        messages.append({"role": "user", "content": user_msg})
        return messages

    async def stream_response(
        self, question: str, conversation_history: List[Message], doc_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        
        chunks = self._retrieve_context(question, doc_ids)
        context = self._build_context_block(chunks)
        sources = self._format_sources(chunks)

        yield {"type": "sources", "sources": [s.dict() for s in sources]}

        messages = self._build_messages(conversation_history, question, context)

        # Send the first model as primary, but provide the rest as instant fallback routing options
        primary_model = self.models_list[0]
        extra_body = {"models": self.models_list} if len(self.models_list) > 1 else None

        full_answer = ""
        try:
            response = await self.client.chat.completions.create(
                model=primary_model,
                messages=messages,
                stream=True,
                extra_body=extra_body  # OpenRouter reads this to bypass traffic congestion
            )
            
            async for chunk in response:
                if len(chunk.choices) > 0:
                    text = chunk.choices[0].delta.content or ""
                    if text:
                        full_answer += text
                        yield {"type": "text", "text": text}
                        
        except Exception as e:
            logger.error(f"OpenRouter routing error: {e}")
            yield {"type": "error", "text": f"AI error: {str(e)}"}
            return

        yield {"type": "done", "answer": full_answer}

    async def get_response(
        self, question: str, conversation_history: List[Message], doc_ids: Optional[List[str]] = None,
    ) -> ChatResponse:
        
        chunks = self._retrieve_context(question, doc_ids)
        context = self._build_context_block(chunks)
        messages = self._build_messages(conversation_history, question, context)

        primary_model = self.models_list[0]
        extra_body = {"models": self.models_list} if len(self.models_list) > 1 else None

        try:
            response = await self.client.chat.completions.create(
                model=primary_model,
                messages=messages,
                stream=False,
                extra_body=extra_body
            )
            answer = response.choices[0].message.content or ""
        except Exception as e:
            answer = f"Error communicating with AI: {str(e)}"

        sources = self._format_sources(chunks)
        updated_history = list(conversation_history) + [
            Message(role="user", content=question),
            Message(role="assistant", content=answer),
        ]
        return ChatResponse(
            answer=answer,
            sources=sources,
            conversation_history=updated_history,
        )

    def _format_sources(self, chunks: List[Dict[str, Any]]) -> List[Source]:
        seen = set()
        sources = []
        for chunk in chunks:
            key = f"{chunk['doc_id']}_{chunk['page']}"
            if key in seen:
                continue
            seen.add(key)
            excerpt = chunk["text"][:300] + ("..." if len(chunk["text"]) > 300 else "")
            sources.append(Source(
                doc_id=chunk["doc_id"],
                filename=chunk["filename"],
                page=chunk["page"],
                excerpt=excerpt,
                score=chunk["score"],
            ))
        return sources