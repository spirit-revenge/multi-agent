import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any
import json
import numpy as np
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)
# Custom local embedding function using sentence-transformers
class LocalEmbeddingFunction:
    def __init__(self, model_name="paraphrase-multilingual-MiniLM-L12-v2", allow_fallback=True):
        self.model_name = model_name
        # Lazy import to avoid module-level import errors when sentence-transformers is not installed
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            self._dimension = self.model.get_embedding_dimension()
            self._using_fallback = False
        except Exception as e:
            # Fallback dummy model to allow testing without the package installed
            logger.warning("sentence_transformers import failed: %s. Using dummy fallback model.", e)
            self._using_fallback = True
            if allow_fallback:
                class _DummyModel:
                    def __init__(self, dim=384):
                        self._dim = dim
                    def get_embedding_dimension(self):
                        return self._dim
                    def encode(self, items, convert_to_numpy=True):
                        import numpy as _np
                        if isinstance(items, str):
                            return _np.zeros(self._dim)
                        return _np.zeros((len(items), self._dim))
                # choose a reasonable default dim
                self.model = _DummyModel(dim=384)
                self._dimension = self.model.get_embedding_dimension()
            else:
                raise
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        # return numpy array (rows = embeddings) so Chroma can call .tolist() if needed
        return self.model.encode(input, convert_to_numpy=True)

    def embed_documents(self, input: List[str]):
        return self.__call__(input)

    def embed_query(self, input: str):
        # return a 1-D numpy array for a single query
        return self.model.encode(input, convert_to_numpy=True)

    def name(self) -> str:
        return f"local-sentence-transformer:{self.model_name}"

    def get_config(self) -> Dict[str, Any]:
        return {"model_name": self.model_name}

    @classmethod
    def build_from_config(cls, config: Dict[str, Any]) -> "LocalEmbeddingFunction":
        return cls(model_name=config["model_name"])
    
    @property
    def dimension(self):
        return self._dimension

class LectureVectorStore:
    def __init__(self, persist_directory="chroma_db", collection_name="lectures"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embedding_fn = LocalEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )
    
    def _get_file_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of file content to detect changes."""
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def _chunk_text(self, text: str, chunk_size=500, overlap=100) -> List[str]:
        """Simple chunking by characters with overlap."""
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks
    
    def index_files(self, folder_path: str, force_reindex=False, progress_callback=None):
        """
        Scan folder, extract text from PDF/PPT, chunk, and index into Chroma.
        Only indexes files that have changed (based on hash) unless force_reindex=True.

        Args:
            folder_path: Path to directory containing PDF/PPTX files
            force_reindex: If True, re-index all files regardless of hash
            progress_callback: Optional callable(status, message) for progress reporting
        """
        if progress_callback:
            progress_callback("indexing", "Scanning files...")

        from tools.local_file_tool import ReadLocalLectureFilesTool
        tool = ReadLocalLectureFilesTool()
        
        # Get all PDF/PPT files
        folder = Path(folder_path)
        files = list(folder.glob("*.pdf")) + list(folder.glob("*.pptx"))
        logger.debug(f"index_files: found {len(files)} files in {folder_path}")

        if progress_callback:
            progress_callback("indexing", f"Found {len(files)} file(s)")

        if not files:
            logger.warning("No PDF/PPT files found in %s", folder_path)
            if progress_callback:
                progress_callback("complete", "No files to index")
            return
        
        # Load existing file hashes from collection metadata (if any)
        existing_hashes = {}
        try:
            metadata = self.collection.metadata or {}
            raw = metadata.get("file_hashes", {})
            if isinstance(raw, str):
                try:
                    existing_hashes = json.loads(raw)
                except Exception:
                    existing_hashes = {}
            elif isinstance(raw, dict):
                existing_hashes = raw
            else:
                existing_hashes = {}
            logger.debug(f"existing_hashes keys: {list(existing_hashes.keys())}")
        except Exception as e:
            logger.debug(f"warning: failed reading collection metadata: {e}")
            existing_hashes = {}
        
        total = len(files)
        for idx, file_path in enumerate(files, start=1):
            logger.debug(f"processing file: {file_path}")
            file_hash = self._get_file_hash(str(file_path))
            logger.debug(f"file_hash: {file_hash}")
            if not force_reindex and existing_hashes.get(str(file_path)) == file_hash:
                logger.debug(f"Skipping {file_path.name} (unchanged)")
                continue

            if progress_callback:
                progress_callback("indexing", f"[{idx}/{total}] Processing {file_path.name}...")

            logger.debug(f"Indexing {file_path.name}...")
            # Extract text
            if file_path.suffix == '.pdf':
                text = tool._read_pdf(file_path)
            else:
                text = tool._read_pptx(file_path)
            
            # Chunk
            chunks = self._chunk_text(text)
            logger.debug(f"created {len(chunks)} chunks for {file_path.name}")
            # Generate ids: file_name + chunk_index + hash
            ids = [f"{file_path.stem}_{i}_{file_hash[:8]}" for i in range(len(chunks))]
            metadatas = [{"source": str(file_path), "chunk": i} for i in range(len(chunks))]
            
            # Add or update in Chroma
            # First remove existing chunks for this file (if any)
            try:
                existing_result = self.collection.get(where={"source": str(file_path)})
                existing_ids = existing_result.get('ids', [])
            except Exception as e:
                logger.debug(f"warning: collection.get failed for {file_path}: {e}")
                existing_ids = []
            if existing_ids:
                logger.debug(f"deleting {len(existing_ids)} existing ids for {file_path.name}")
                try:
                    self.collection.delete(ids=existing_ids)
                except Exception as e:
                    logger.debug(f"warning: failed to delete existing ids: {e}")
            # Add new chunks
            try:
                pre_count = self.collection.count()
                self.collection.add(
                    ids=ids,
                    documents=chunks,
                    metadatas=metadatas
                )
                post_count = self.collection.count()
                logger.debug(f"collection count before add: {pre_count}, after add: {post_count}")
            except Exception as e:
                logger.debug(f"error: failed to add chunks for {file_path}: {e}")
            # Update hash in collection metadata
            existing_hashes[str(file_path)] = file_hash

            if progress_callback:
                progress_callback("indexing", f"[{idx}/{total}] Indexed {len(chunks)} chunks from {file_path.name}")

        # Save updated hashes to collection metadata (serialize as JSON string)
        try:
            self.collection.modify(metadata={"file_hashes": json.dumps(existing_hashes)})
        except Exception as e:
            logger.debug(f"warning: failed to modify collection metadata: {e}")
        total_chunks = self.collection.count()
        logger.info("Indexing complete. Total chunks: %d", total_chunks)

        if progress_callback:
            progress_callback("complete", f"Indexing complete. Total chunks: {total_chunks}")
    
    def retrieve(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant chunks."""
        results = self.collection.query(query_texts=[query], n_results=k)
        if not results['documents']:
            return []
        documents = results['documents'][0]
        metadatas = results['metadatas'][0]
        distances = results['distances'][0] if results.get('distances') else [0]*len(documents)
        return [
            {"content": doc, "source": meta['source'], "chunk": meta['chunk'], "distance": dist}
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]
    
    def get_context_for_query(self, query: str, k: int = 5) -> str:
        """Return formatted context string for prompt injection."""
        chunks = self.retrieve(query, k)
        if not chunks:
            return ""
        context = "Relevant excerpts from your lectures:\n\n"
        for i, chunk in enumerate(chunks, 1):
            context += f"[{i}] From {Path(chunk['source']).name} (similarity: {1-chunk['distance']:.2f}):\n{chunk['content']}\n\n"
        return context