"""Concrete implementations of the core interfaces.

Provides:
- ``RecursiveCharacterChunker``  – boundary-aware text splitter.
- ``LocalSentenceEmbedder``     – local HuggingFace embedding via ``sentence-transformers``.
- ``PDFDocumentProcessor``      – PDF-to-text extraction via ``PyMuPDF``.
"""

import fitz  # PyMuPDF
from typing import List
from loguru import logger
from src.interfaces import Chunker, Embedder, DocumentProcessor
from sentence_transformers import SentenceTransformer

class RecursiveCharacterChunker(Chunker):
    """Splits text into overlapping chunks, preferring natural boundaries.

    The algorithm greedily takes ``chunk_size`` characters, then searches
    backwards for the nearest newline or space to produce cleaner splits.
    Adjacent chunks overlap by ``chunk_overlap`` characters to preserve
    cross-boundary context for downstream embedding.
    """
    def chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        # Simple character-based splitting implementation
        # For a robust implementation, consider langchain.text_splitter
        chunks = []
        if not text:
            return chunks

        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            
            # If we're at the end of the text, take the rest
            if end >= text_length:
                chunks.append(text[start:])
                break
                
            # Try to find a nice boundary to split at (e.g. newline or space)
            # Find the last newline in the chunk
            last_newline = text.rfind('\n', start, end)
            if last_newline != -1 and last_newline > start + (chunk_size // 2):
                end = last_newline + 1
            else:
                # Find the last space
                last_space = text.rfind(' ', start, end)
                if last_space != -1 and last_space > start + (chunk_size // 2):
                    end = last_space + 1
                    
            chunks.append(text[start:end].strip())
            start = end - chunk_overlap
            
            # Ensure we make progress if overlap causes us to get stuck
            if start <= start - chunk_overlap:
                start += 1
                
        return [c for c in chunks if c.strip()]


class LocalSentenceEmbedder(Embedder):
    """Generates dense vector embeddings using a local ``SentenceTransformer`` model.

    Args:
        model_name: HuggingFace model identifier (default ``all-MiniLM-L6-v2``,
            384-dim, good speed/quality trade-off). Override via ``EMBEDDER_MODEL``
            environment variable.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info("Loading embedding model '{}' ...", model_name)
        self.model = SentenceTransformer(model_name)
        
    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

class PDFDocumentProcessor(DocumentProcessor):
    """Extracts text from PDF files using PyMuPDF."""
    def process_bytes(self, content: bytes, filename: str) -> str:
        text = ""
        try:
            # Using PyMuPDF to extract text from raw bytes
            doc = fitz.open(stream=content, filetype="pdf")
            for page in doc:
                text += page.get_text()
            doc.close()
        except Exception as e:
            logger.error("Error processing '{}': {}", filename, e)
            
        return text.strip()
