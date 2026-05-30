"""
Vector store for lecture documents with multi-modal content support.

Supports:
- Text: semantic chunking, stored as vectorized documents
- Images: extracted, described via BLIP, description stored as searchable text + image saved to disk
- Tables: converted to Markdown, stored as searchable text
- All entries have timestamps and content-type metadata
- Incremental indexing via SHA256 file hashes
"""

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import chromadb

from tools.document_processor import process_document
from tools.image_captioner import describe_images_batch

logger = logging.getLogger(__name__)

# ============================================================================
# Embedding function (reused from original; uses sentence-transformers)
# ============================================================================

class LocalEmbeddingFunction:
    """Custom embedding function using sentence-transformers (multilingual)."""

    def __init__(self, model_name="paraphrase-multilingual-MiniLM-L12-v2", allow_fallback=True):
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            self._dimension = self.model.get_embedding_dimension()
        except Exception as e:
            logger.warning("sentence_transformers import failed: %s. Using dummy fallback.", e)
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
                self.model = _DummyModel(dim=384)
                self._dimension = self.model.get_embedding_dimension()
            else:
                raise

    def __call__(self, input):
        return self.model.encode(input, convert_to_numpy=True)

    def embed_documents(self, input):
        return self.__call__(input)

    def embed_query(self, input):
        return self.model.encode(input, convert_to_numpy=True)

    def name(self) -> str:
        return f"local-sentence-transformer:{self.model_name}"

    def get_config(self) -> Dict[str, Any]:
        return {"model_name": self.model_name}

    @classmethod
    def build_from_config(cls, config):
        return cls(model_name=config["model_name"])

    @property
    def dimension(self):
        return self._dimension


# ============================================================================
# LectureVectorStore — main class
# ============================================================================

class LectureVectorStore:
    """Multi-modal vector store for lecture documents.

    Stores three content types in a single ChromaDB collection,
    distinguished by the ``type`` metadata field:
    - ``"text"``   → the chunked paragraph text
    - ``"image"``  → the image description text (image saved to images/ dir)
    - ``"table"``  → the Markdown table string
    """

    def __init__(
        self,
        persist_directory: str = "chroma_db",
        images_directory: str = "images",
        collection_name: str = "lectures",
    ):
        self.persist_directory = Path(persist_directory)
        self.images_directory = Path(images_directory)
        self.collection_name = collection_name

        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.images_directory.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.embedding_fn = LocalEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    @staticmethod
    def _get_file_hash(file_path: str) -> str:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    # ------------------------------------------------------------------
    # File hash bookkeeping (stored in collection metadata)
    # ------------------------------------------------------------------

    def _load_file_hashes(self) -> Dict[str, str]:
        try:
            meta = self.collection.metadata or {}
            raw = meta.get("file_hashes", {})
            if isinstance(raw, str):
                return json.loads(raw)
            if isinstance(raw, dict):
                return raw
        except Exception:
            pass
        return {}

    def _save_file_hashes(self, hashes: Dict[str, str]):
        self.collection.modify(metadata={"file_hashes": json.dumps(hashes)})

    # ------------------------------------------------------------------
    # Indexing (single file or all files)
    # ------------------------------------------------------------------

    def index_files(
        self,
        folder_path: str,
        force_reindex: bool = False,
        progress_callback: Optional[Callable] = None,
    ):
        """Scan a folder and index changed/new files.

        Args:
            folder_path: Path to directory containing PDF/PPTX/DOCX files.
            force_reindex: If True, re-index all files regardless of hash.
            progress_callback: Optional callable(status, message).
        """
        if progress_callback:
            progress_callback("indexing", "扫描文件中...")

        folder = Path(folder_path)
        files = (
            list(folder.glob("*.pdf"))
            + list(folder.glob("*.pptx"))
            + list(folder.glob("*.docx"))
        )

        if not files:
            logger.warning("No PDF/PPTX/DOCX files found in %s", folder_path)
            if progress_callback:
                progress_callback("complete", "未找到可索引的文件")
            return

        existing_hashes = self._load_file_hashes()
        changed_files = []

        for f in files:
            f_hash = self._get_file_hash(str(f))
            if not force_reindex and existing_hashes.get(str(f)) == f_hash:
                continue
            changed_files.append((f, f_hash))

        if not changed_files:
            logger.info("All files are up-to-date.")
            if progress_callback:
                progress_callback("complete", "所有文件已是最新")
            return

        total = len(changed_files)
        for idx, (file_path, file_hash) in enumerate(changed_files, start=1):
            if progress_callback:
                progress_callback("indexing", f"[{idx}/{total}] 处理 {file_path.name}...")

            self._index_single_file(file_path)

            existing_hashes[str(file_path)] = file_hash
            if progress_callback:
                progress_callback("indexing", f"[{idx}/{total}] 完成 {file_path.name}")

        self._save_file_hashes(existing_hashes)

        total_entries = self.collection.count()
        logger.info("Indexing complete. Total entries in collection: %d", total_entries)
        if progress_callback:
            progress_callback("complete", f"索引完成，共 {total_entries} 条记录")

    def _index_single_file(self, file_path: Path):
        """Process and index a single document into ChromaDB.

        Steps:
        1. Process the document → text chunks, images, tables
        2. Describe images via BLIP
        3. Save images to disk
        4. Store everything in ChromaDB with type/timestamp metadata
        """
        timestamp = datetime.now().isoformat(timespec="seconds")

        # 1. Process the document
        result = process_document(str(file_path))

        # 2. Describe images (batch)
        described = describe_images_batch(result["images"])

        # -- Remove old entries for this file --
        self._delete_file_entries(file_path)

        # -- Prepare new entries --
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict] = []

        # --- Text chunks ---
        for i, chunk in enumerate(result["texts"]):
            if not chunk.strip():
                continue
            ids.append(f"{file_path.stem}_text_{i}")
            documents.append(chunk)
            metadatas.append({
                "type": "text",
                "source": str(file_path),
                "chunk_index": i,
                "indexed_at": timestamp,
            })

        # --- Image descriptions ---
        for i, (desc, pil_img, img_filename) in enumerate(described):
            # Save image to disk
            img_path = self.images_directory / img_filename
            pil_img.save(str(img_path), "PNG")

            ids.append(f"{file_path.stem}_img_{i}")
            documents.append(desc)
            metadatas.append({
                "type": "image",
                "source": str(file_path),
                "chunk_index": i,
                "indexed_at": timestamp,
                "image_path": str(img_path),
                "image_filename": img_filename,
            })

        # --- Table Markdown ---
        for i, md_table in enumerate(result["tables"]):
            if not md_table.strip():
                continue
            ids.append(f"{file_path.stem}_table_{i}")
            documents.append(md_table)
            metadatas.append({
                "type": "table",
                "source": str(file_path),
                "chunk_index": i,
                "indexed_at": timestamp,
            })

        # -- Batch add to ChromaDB --
        if ids:
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            logger.info(
                "Indexed %s: %d text, %d images, %d tables",
                file_path.name,
                len(result["texts"]),
                len(described),
                len(result["tables"]),
            )
        else:
            logger.warning("No content extracted from %s", file_path.name)

    def _delete_file_entries(self, file_path: Path) -> int:
        """Remove all ChromaDB entries and image files for a given source file.

        Returns:
            Number of entries removed.
        """
        try:
            existing = self.collection.get(where={"source": str(file_path)})
            existing_ids = existing.get("ids", [])
            existing_metadatas = existing.get("metadatas", [])
        except Exception:
            return 0

        if not existing_ids:
            return

        # Remove associated image files from disk
        for meta in existing_metadatas:
            if meta and meta.get("type") == "image":
                img_path = meta.get("image_path")
                if img_path:
                    try:
                        Path(img_path).unlink(missing_ok=True)
                    except Exception:
                        pass

        # Remove from ChromaDB
        try:
            self.collection.delete(ids=existing_ids)
            logger.debug("Deleted %d old entries for %s", len(existing_ids), file_path.name)
        except Exception as e:
            logger.warning("Failed to delete old entries for %s: %s", file_path.name, e)

        return len(existing_ids)

        return len(existing_ids)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        k: int = 5,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant entries.

        Args:
            query: User question text.
            k: Number of results to return.
            content_type: Optional filter — "text", "image", "table", or None (all).

        Returns:
            List of dicts with keys: content, source, type, chunk_index, indexed_at,
            distance, (image_path if type=image).
        """
        where = None
        if content_type:
            where = {"type": content_type}

        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where=where,
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        entries = []
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results.get("distances", [None])[0]
        if distances is None:
            distances = [0.0] * len(documents)

        for doc, meta, dist in zip(documents, metadatas, distances):
            entry = {
                "content": doc,
                "source": Path(meta.get("source", "")).name,
                "type": meta.get("type", "text"),
                "chunk_index": meta.get("chunk_index", 0),
                "indexed_at": meta.get("indexed_at", ""),
                "similarity": 1 - dist if dist else 0,
            }
            if meta.get("type") == "image" and meta.get("image_path"):
                entry["image_path"] = meta["image_path"]
            entries.append(entry)

        return entries

    def get_context_for_query(
        self,
        query: str,
        k: int = 5,
    ) -> str:
        """Return formatted context string for prompt injection (backward-compatible).

        Retrieves text + image descriptions + tables, then formats them
        as a single string the Agent can read.
        """
        from urllib.parse import quote
        entries = self.retrieve(query, k)
        if not entries:
            return ""

        context = "以下是与问题相关的讲座内容：\n\n"
        text_idx = 1
        for entry in entries:
            tag = {"text": "📝 文本", "image": "🖼️ 图片", "table": "📊 表格"}.get(
                entry["type"], "📄 内容"
            )
            similarity = entry["similarity"]
            context += (
                f"[{text_idx}] {tag} — 来源：{entry['source']} "
                f"(相关度：{similarity:.2f})\n"
            )
            context += f"{entry['content']}\n\n"
            if entry.get("image_path"):
                # Include image reference as Markdown
                # quote() doesn't encode underscores, but Markdown renderers
                # treat _ as italic markers → break the URL. Encode _ as %5F.
                img_filename = Path(entry["image_path"]).name
                safe_name = quote(img_filename).replace('_', '%5F')
                context += f"![{entry['content']}](/images/{safe_name})\n\n"
            text_idx += 1

        # Tell the agent to use the actual image references above — do NOT invent new paths
        context += "注意：上述每张图片后面都已附带了正确的 Markdown 引用路径，**直接复制即可**。不要自己编造 /images/ 路径。\n"

        return context

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_file(self, source_path: str) -> int:
        """Remove all entries for a given source file path.

        Also deletes associated image files from the images/ directory.

        Args:
            source_path: The file path string (same as stored in metadata["source"]).

        Returns:
            Number of entries removed.
        """
        return self._delete_file_entries(Path(source_path))

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count(self) -> int:
        return self.collection.count()

    def get_stats(self) -> Dict[str, Any]:
        """Return collection statistics."""
        try:
            all_data = self.collection.get()
            types = {}
            for meta in (all_data.get("metadatas") or []):
                if meta:
                    t = meta.get("type", "unknown")
                    types[t] = types.get(t, 0) + 1
            return {
                "total": len(all_data.get("ids", [])),
                "by_type": types,
            }
        except Exception as e:
            return {"total": 0, "by_type": {}, "error": str(e)}
