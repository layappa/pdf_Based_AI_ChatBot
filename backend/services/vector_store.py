import os
import logging
from typing import List, Dict, Any, Optional
import uuid

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB-backed vector store with sentence-transformers embeddings.
    
    Embedding Model: all-MiniLM-L6-v2
    - Fast, lightweight (80MB), good quality for semantic search
    - 384-dimensional embeddings
    - Runs locally, no API calls needed for embeddings
    
    Retrieval: Cosine similarity with optional BM25 hybrid re-ranking
    """

    COLLECTION_NAME = "pdf_chunks"
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"

    def __init__(self):
        self._client = None
        self._collection = None
        self._embedder = None
        self._documents: Dict[str, Dict] = {}  # doc registry in memory
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        self._init_chromadb()
        self._init_embedder()
        self._initialized = True

    def _init_chromadb(self):
        import chromadb
        from chromadb.config import Settings

        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_data")
        os.makedirs(persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB initialized with {self._collection.count()} existing chunks")

    def _init_embedder(self):
        from sentence_transformers import SentenceTransformer
        model_name = os.environ.get("EMBEDDING_MODEL", self.EMBEDDING_MODEL)
        logger.info(f"Loading embedding model: {model_name}")
        self._embedder = SentenceTransformer(model_name)
        logger.info("Embedding model loaded")

    def _embed(self, texts: List[str]) -> List[List[float]]:
        self._ensure_initialized()
        embeddings = self._embedder.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()

    async def add_chunks(self, chunks: List[Dict[str, Any]]):
        """Add document chunks to the vector store."""
        self._ensure_initialized()
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        embeddings = self._embed(texts)

        ids = [c["id"] for c in chunks]
        metadatas = [
            {
                "doc_id": c["doc_id"],
                "filename": c["filename"],
                "page": c["page"],
                "pages": ",".join(str(p) for p in c["pages"]),
                "chunk_index": c["chunk_index"],
            }
            for c in chunks
        ]

        # Add in batches of 100
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            self._collection.add(
                ids=ids[i:i+batch_size],
                embeddings=embeddings[i:i+batch_size],
                documents=texts[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
            )

        logger.info(f"Added {len(chunks)} chunks to vector store")

    def search(
        self,
        query: str,
        n_results: int = 5,
        doc_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with optional document filtering.
        Returns top-k chunks with similarity scores.
        """
        self._ensure_initialized()

        if self._collection.count() == 0:
            return []

        query_embedding = self._embed([query])[0]

        where = None
        if doc_ids:
            if len(doc_ids) == 1:
                where = {"doc_id": doc_ids[0]}
            else:
                where = {"doc_id": {"$in": doc_ids}}

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self._collection.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

        chunks = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i]
                score = 1 - distance  # cosine distance → similarity

                meta = results["metadatas"][0][i]
                chunks.append({
                    "id": chunk_id,
                    "text": results["documents"][0][i],
                    "doc_id": meta["doc_id"],
                    "filename": meta["filename"],
                    "page": meta["page"],
                    "pages": [int(p) for p in meta.get("pages", str(meta["page"])).split(",")],
                    "score": round(score, 4),
                })

        return chunks

    def hybrid_search(
        self,
        query: str,
        n_results: int = 5,
        doc_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: combine semantic search with BM25 keyword scoring.
        Falls back to semantic-only if rank_bm25 not available.
        """
        semantic_results = self.search(query, n_results=n_results * 2, doc_ids=doc_ids)

        try:
            from rank_bm25 import BM25Okapi
            if not semantic_results:
                return []

            corpus = [r["text"].lower().split() for r in semantic_results]
            bm25 = BM25Okapi(corpus)
            query_tokens = query.lower().split()
            bm25_scores = bm25.get_scores(query_tokens)

            # Normalize BM25 scores
            max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
            bm25_normalized = [s / max_bm25 for s in bm25_scores]

            # Combine: 70% semantic + 30% BM25
            for i, result in enumerate(semantic_results):
                result["score"] = round(
                    0.7 * result["score"] + 0.3 * bm25_normalized[i], 4
                )

            # Re-rank and deduplicate
            semantic_results.sort(key=lambda x: x["score"], reverse=True)
            return semantic_results[:n_results]

        except ImportError:
            logger.info("rank_bm25 not available, using semantic search only")
            return semantic_results[:n_results]

    def register_document(self, doc_id: str, filename: str, chunks: int, pages: int):
        """Register document metadata."""
        self._documents[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": chunks,
            "pages": pages,
        }

    def list_documents(self) -> List[Dict]:
        return list(self._documents.values())

    def delete_document(self, doc_id: str) -> bool:
        """Delete all chunks for a document."""
        self._ensure_initialized()
        if doc_id not in self._documents:
            return False

        try:
            self._collection.delete(where={"doc_id": doc_id})
            del self._documents[doc_id]
            return True
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            return False
