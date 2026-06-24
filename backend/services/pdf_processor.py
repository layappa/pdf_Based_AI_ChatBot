import io
import uuid
import re
from typing import Tuple, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Processes PDF files: extracts text, splits into chunks, and stores embeddings.
    
    Chunking Strategy:
    - Semantic chunking: splits on paragraph boundaries first, then by token count
    - Chunk size: ~500 tokens with 100-token overlap
    - Preserves page number metadata for source attribution
    - Cleans extracted text (removes hyphenation, normalizes whitespace)
    """

    CHUNK_SIZE = 500        # target tokens per chunk (~375 words)
    CHUNK_OVERLAP = 100     # overlap tokens between chunks
    WORDS_PER_TOKEN = 0.75  # rough conversion

    async def process(
        self,
        pdf_bytes: bytes,
        filename: str,
        vector_store
    ) -> Tuple[str, int, int]:
        """
        Extract text from PDF, chunk it, embed it, and store in vector store.
        Returns (doc_id, chunk_count, page_count).
        """
        doc_id = str(uuid.uuid4())

        try:
            import pypdf
            pages = self._extract_pages_pypdf(pdf_bytes)
        except Exception as e:
            logger.warning(f"pypdf failed: {e}, trying pdfplumber")
            try:
                import pdfplumber
                pages = self._extract_pages_pdfplumber(pdf_bytes)
            except Exception as e2:
                raise RuntimeError(f"Could not extract text from PDF: {e2}")

        if not pages:
            raise ValueError("No text could be extracted from the PDF")

        chunks = self._create_chunks(pages, doc_id, filename)

        if not chunks:
            raise ValueError("No chunks created from PDF content")

        await vector_store.add_chunks(chunks)

        vector_store.register_document(doc_id, filename, len(chunks), len(pages))

        logger.info(f"Processed {filename}: {len(pages)} pages, {len(chunks)} chunks")
        return doc_id, len(chunks), len(pages)

    def _extract_pages_pypdf(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text per page using pypdf."""
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = self._clean_text(text)
            if text.strip():
                pages.append({"page": i + 1, "text": text})
        return pages

    def _extract_pages_pdfplumber(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text per page using pdfplumber (better for complex layouts)."""
        import pdfplumber
        pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                text = self._clean_text(text)
                if text.strip():
                    pages.append({"page": i + 1, "text": text})
        return pages

    def _clean_text(self, text: str) -> str:
        """Clean extracted PDF text."""
        # Fix hyphenated line breaks
        text = re.sub(r"-\n(\w)", r"\1", text)
        # Normalize whitespace but preserve paragraph breaks
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove non-printable characters
        text = re.sub(r"[^\x20-\x7E\n]", " ", text)
        return text.strip()

    def _create_chunks(
        self,
        pages: List[Dict[str, Any]],
        doc_id: str,
        filename: str
    ) -> List[Dict[str, Any]]:
        """
        Split pages into overlapping chunks.
        Strategy: paragraph-aware splitting with sliding window overlap.
        """
        chunks = []
        chunk_index = 0

        # Collect all paragraphs with their page numbers
        all_paragraphs = []
        for page_data in pages:
            paragraphs = [p.strip() for p in page_data["text"].split("\n\n") if p.strip()]
            for para in paragraphs:
                # Further split very long paragraphs by sentences
                if self._word_count(para) > self.CHUNK_SIZE * 1.5:
                    sentences = self._split_sentences(para)
                    for s in sentences:
                        if s.strip():
                            all_paragraphs.append({"page": page_data["page"], "text": s.strip()})
                else:
                    all_paragraphs.append({"page": page_data["page"], "text": para})

        # Build chunks by accumulating paragraphs up to CHUNK_SIZE
        current_texts = []
        current_pages = set()
        current_words = 0
        overlap_buffer = []

        for para_data in all_paragraphs:
            words = self._word_count(para_data["text"])

            if current_words + words > self.CHUNK_SIZE and current_texts:
                # Save current chunk
                chunk_text = "\n\n".join(current_texts)
                chunks.append(self._make_chunk(
                    chunk_text, doc_id, filename,
                    sorted(current_pages), chunk_index
                ))
                chunk_index += 1

                # Keep overlap: last N words worth of paragraphs
                overlap_buffer = []
                overlap_words = 0
                for t in reversed(current_texts):
                    tw = self._word_count(t)
                    if overlap_words + tw <= self.CHUNK_OVERLAP:
                        overlap_buffer.insert(0, t)
                        overlap_words += tw
                    else:
                        break

                current_texts = overlap_buffer.copy()
                current_pages = {para_data["page"]}
                current_words = overlap_words

            current_texts.append(para_data["text"])
            current_pages.add(para_data["page"])
            current_words += words

        # Save the final chunk
        if current_texts:
            chunk_text = "\n\n".join(current_texts)
            chunks.append(self._make_chunk(
                chunk_text, doc_id, filename,
                sorted(current_pages), chunk_index
            ))

        return chunks

    def _make_chunk(
        self,
        text: str,
        doc_id: str,
        filename: str,
        pages: List[int],
        index: int
    ) -> Dict[str, Any]:
        return {
            "id": f"{doc_id}_{index}",
            "doc_id": doc_id,
            "filename": filename,
            "text": text,
            "pages": pages,
            "page": pages[0] if pages else 1,  # primary page
            "chunk_index": index,
        }

    def _word_count(self, text: str) -> int:
        return len(text.split())

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        # Group sentences into ~CHUNK_SIZE/3 word groups
        groups = []
        current = []
        current_words = 0
        target = self.CHUNK_SIZE // 3

        for sent in sentences:
            words = self._word_count(sent)
            if current_words + words > target and current:
                groups.append(" ".join(current))
                current = [sent]
                current_words = words
            else:
                current.append(sent)
                current_words += words

        if current:
            groups.append(" ".join(current))

        return groups
