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
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import chromadb

from tools.document_processor import process_document
from tools.image_captioner import describe_images_batch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query Rewrite — expand abbreviations for better embedding matching
# ---------------------------------------------------------------------------

QUERY_REWRITE_MAP = {
    # English acronyms → full English + Chinese
    "rag": "Retrieval Augmented Generation 检索增强生成",
    "llm": "Large Language Model 大语言模型",
    "nlp": "Natural Language Processing 自然语言处理",
    "gpt": "GPT Generative Pre-trained Transformer 生成式预训练",
    "bert": "BERT Bidirectional Encoder 双向编码器",
    "cnn": "CNN Convolutional Neural Network 卷积神经网络",
    "rnn": "RNN Recurrent Neural Network 循环神经网络",
    "lstm": "LSTM Long Short Term Memory 长短期记忆",
    "transformer": "Transformer 注意力机制 自注意力",
    "attention": "Attention 注意力机制 权重",
    "embedding": "Embedding 嵌入 向量化",
    "tokenizer": "Tokenizer 分词器 令牌化",
    "fine.?tune": "fine tune 微调 参数调整",
    "prompt": "Prompt 提示词 指令",
    "agent": "Agent 智能体 代理",
    "multi.?modal": "multimodal 多模态 多模式",
    "few.?shot": "few shot 少样本 小样本",
    "zero.?shot": "zero shot 零样本",
}


def rewrite_query(query: str) -> str:
    """Expand abbreviations and add Chinese equivalents for better embedding matching.

    Uses rule-based lookup only — no LLM call.
    Handles Chinese context where \b boundaries don't apply.
    Example: "介绍一下rag" → "介绍一下rag (Retrieval Augmented Generation 检索增强生成)"
    """
    lower = query.lower()
    for abbrev, expansion in QUERY_REWRITE_MAP.items():
        if abbrev in lower:
            # Check if the full terms (excluding the abbreviation itself) are already present
            full_terms = [t for t in expansion.lower().split()[:4] if t != abbrev]
            if not any(term in lower for term in full_terms):
                query = query + f" ({expansion})"
                break
    return query


# ---------------------------------------------------------------------------
# Retrieval Cache — avoid re-querying ChromaDB for similar questions
# ---------------------------------------------------------------------------

class RetrievalCache:
    """Simple file-based cache for RAG retrieval results.

    Normalizes queries (same scheme as AnswerCache) so rephrasings hit.
    """

    _CACHE_FILE = "cache/retrieval_cache.json"
    _MAX_ENTRIES = 100

    def __init__(self):
        import re
        self._re = re
        self._cache: dict[str, list] = {}
        self._load()

    def _normalize(self, query: str) -> str:
        import hashlib
        q = query.lower().strip()
        q = self._re.sub(r"[^\w\s]", " ", q)
        q = self._re.sub(r"\s+", " ", q).strip()
        tokens = sorted(q.split())
        normalized = " ".join(tokens) if tokens else q
        return hashlib.md5(normalized.encode()).hexdigest()

    def _load(self):
        try:
            path = Path(self._CACHE_FILE)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self._cache = data.get("entries", {})
        except Exception:
            self._cache = {}

    def _save(self):
        try:
            path = Path(self._CACHE_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Trim to max size
            if len(self._cache) > self._MAX_ENTRIES:
                keys = list(self._cache.keys())[-self._MAX_ENTRIES:]
                self._cache = {k: self._cache[k] for k in keys}
            path.write_text(
                json.dumps({"entries": self._cache}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get(self, query: str) -> list | None:
        key = self._normalize(query)
        return self._cache.get(key)

    def set(self, query: str, entries: list):
        key = self._normalize(query)
        # Only store serializable data (strip numpy arrays)
        clean = []
        for e in entries:
            clean.append({
                "content": e["content"],
                "source": e["source"],
                "type": e["type"],
                "similarity": float(e.get("similarity", 0)),
            })
        self._cache[key] = clean
        self._save()

    def clear(self):
        self._cache = {}
        self._save()


retrieval_cache = RetrievalCache()


# ---------------------------------------------------------------------------
# BM25 — simple implementation, no external dependencies
# ---------------------------------------------------------------------------

class _BM25Index:
    """Lightweight BM25 Okapi index for hybrid retrieval.

    Built from ChromaDB collection contents on demand.
    """

    def __init__(self):
        self._corpus: list[str] = []
        self._avgdl: float = 0.0
        self._idf: dict[str, float] = {}
        self._doc_lens: list[int] = []
        self._k1 = 1.5
        self._b = 0.75
        self._dirty = True

    def _tokenize(self, text: str) -> list[str]:
        import re
        # Split on whitespace and common Chinese punctuation
        tokens = re.findall(r"[a-zA-Z0-9_]+|[^\s\w]", text.lower())
        # Filter out single punctuation characters that aren't useful for matching
        return [t for t in tokens if len(t) > 1 or t.isalnum()]

    def build(self, documents: list[str]):
        """Build/rebuild the index from a list of document strings."""
        self._corpus = documents
        self._doc_lens = [len(self._tokenize(d)) for d in documents]
        n = len(documents)
        self._avgdl = sum(self._doc_lens) / n if n > 0 else 1.0

        # Compute IDF
        import math
        doc_freq: dict[str, int] = {}
        for doc in documents:
            seen = set(self._tokenize(doc))
            for token in seen:
                doc_freq[token] = doc_freq.get(token, 0) + 1

        self._idf = {
            token: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
            for token, freq in doc_freq.items()
        }
        self._dirty = False

    def score(self, query: str, doc_idx: int) -> float:
        """Compute BM25 score for a single query-document pair."""
        if self._dirty or doc_idx >= len(self._corpus):
            return 0.0
        query_tokens = self._tokenize(query)
        doc_tokens = self._tokenize(self._corpus[doc_idx])
        doc_len = self._doc_lens[doc_idx]

        score = 0.0
        for token in query_tokens:
            if token not in self._idf:
                continue
            tf = doc_tokens.count(token)
            if tf == 0:
                continue
            idf = self._idf[token]
            numerator = tf * (self._k1 + 1)
            denominator = tf + self._k1 * (1 - self._b + self._b * doc_len / self._avgdl)
            score += idf * numerator / denominator
        return score

    def scores(self, query: str, indices: list[int] | None = None) -> dict[int, float]:
        """Score multiple documents at once.

        Returns {doc_idx: bm25_score} for the given indices (or all if None).
        """
        if self._dirty:
            return {}
        check = indices if indices is not None else range(len(self._corpus))
        return {i: self.score(query, i) for i in check if i < len(self._corpus)}


_bm25 = _BM25Index()

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

    def index_file(self, file_path: str):
        """Index a single file directly (no directory scan).

        Much faster than ``index_files()`` for single uploads because it
        skips the SHA256 scan of every file in the folder.

        Args:
            file_path: Absolute or relative path to a PDF/PPTX/DOCX file.
        """
        fp = Path(file_path)
        if not fp.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = fp.suffix.lower()
        if ext not in ('.pdf', '.pptx', '.docx'):
            raise ValueError(f"Unsupported file type: {ext}")

        logger.info("Indexing single file: %s", fp.name)
        self._index_single_file(fp)

        # Update file hash so future index_files() skips it
        try:
            f_hash = self._get_file_hash(str(fp))
            hashes = self._load_file_hashes()
            hashes[str(fp)] = f_hash
            self._save_file_hashes(hashes)
        except Exception:
            pass

        total = self.collection.count()
        logger.info("Indexed %s. Total collection entries: %d", fp.name, total)

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
        failed = []
        for idx, (file_path, file_hash) in enumerate(changed_files, start=1):
            if progress_callback:
                progress_callback("indexing", f"[{idx}/{total}] 处理 {file_path.name}...")

            try:
                self._index_single_file(file_path)
                existing_hashes[str(file_path)] = file_hash
            except Exception as e:
                logger.exception("Failed to index %s: %s", file_path.name, e)
                failed.append(file_path.name)
                # Continue with next file — don't let one bad file block everything

            if progress_callback:
                progress_callback("indexing", f"[{idx}/{total}] 完成 {file_path.name}")

        self._save_file_hashes(existing_hashes)

        if failed:
            logger.warning("Indexing complete with %d failures: %s", len(failed), failed)

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
        file_stem = file_path.stem
        # Include path hash in IDs so files with identical stems (e.g., from
        # different directories) don't collide in ChromaDB.
        path_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
        id_prefix = f"{file_stem}_{path_hash}"

        # 1. Process the document
        result = process_document(str(file_path))

        # 2. Describe images (batch)
        described = describe_images_batch(result["images"])

        # -- Capture old entries BEFORE adding new ones --
        old_ids = []
        old_image_paths = []
        try:
            existing = self.collection.get(where={"source": str(file_path)})
            old_ids = existing.get("ids", [])
            for meta in existing.get("metadatas", []):
                if meta and meta.get("type") == "image":
                    img_path = meta.get("image_path")
                    if img_path:
                        old_image_paths.append(img_path)
        except Exception:
            pass

        # -- Prepare new entries --
        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict] = []

        # --- Text chunks ---
        for i, chunk in enumerate(result["texts"]):
            if not chunk.strip():
                continue
            ids.append(f"{id_prefix}_text_{i}")
            documents.append(chunk)
            metadatas.append({
                "type": "text",
                "source": str(file_path),
                "chunk_index": i,
                "indexed_at": timestamp,
            })

        # --- Image descriptions ---
        for i, (desc, pil_img, img_filename) in enumerate(described):
            # Save image to disk (resolve to absolute path for reliable later deletion)
            img_path = (self.images_directory / img_filename).resolve()
            pil_img.save(str(img_path), "PNG")

            ids.append(f"{id_prefix}_img_{i}")
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
            ids.append(f"{id_prefix}_table_{i}")
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

            # Delete old entries by ID — but only those that don't overlap with
            # the new IDs.  When force_reindex=True and the file hasn't changed,
            # old and new IDs are identical; deleting would wipe the fresh data.
            removed = 0
            if old_ids:
                new_id_set = set(ids)
                stale_ids = [oid for oid in old_ids if oid not in new_id_set]
                if stale_ids:
                    try:
                        self.collection.delete(ids=stale_ids)
                        removed = len(stale_ids)
                    except Exception as e:
                        logger.warning("Failed to delete old entries: %s", e)
            # Only delete old image files that are NOT referenced by new entries.
            # (When the document hasn't changed, old and new filenames are the
            # same — deleting them would wipe out the images we just saved.)
            new_image_paths = {
                (self.images_directory / fn).resolve() for _, _, fn in described
                if fn
            }
            for img_path in old_image_paths:
                try:
                    p = Path(img_path).resolve()
                    if p not in new_image_paths and p.exists():
                        p.unlink(missing_ok=True)
                except Exception:
                    pass

            logger.info(
                "Indexed %s: %d text, %d images, %d tables (removed %d old entries)",
                file_path.name,
                len(result["texts"]),
                len(described),
                len(result["tables"]),
                removed,
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
            return 0

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

    # ------------------------------------------------------------------
    # Web search result indexing
    # ------------------------------------------------------------------

    def index_web_search(self, query: str, facts: list, urls: list = None):
        """Index web search results into ChromaDB so future similar queries
        can retrieve them via the RAG pipeline.

        Uses ``type="web"`` metadata so results are distinguishable from
        lecture content.  Old entries for the same query are deleted before
        re-indexing (dedup by query hash).
        """
        if not facts:
            return

        if urls is None:
            urls = []

        timestamp = datetime.now().isoformat(timespec="seconds")
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        source = f"web_search:{query_hash}"

        # Delete old entries for this query (dedup)
        try:
            existing = self.collection.get(where={"source": source})
            existing_ids = existing.get("ids", [])
            if existing_ids:
                self.collection.delete(ids=existing_ids)
        except Exception:
            pass

        ids = []
        documents = []
        metadatas = []

        for i, fact in enumerate(facts):
            fact_text = fact.strip()
            if not fact_text:
                continue
            ids.append(f"web_{query_hash}_{i}")
            documents.append(fact_text)
            metadatas.append({
                "type": "web",
                "source": source,
                "chunk_index": i,
                "indexed_at": timestamp,
                "web_query": query,
                "urls": json.dumps(urls, ensure_ascii=False),
            })

        if ids:
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            _bm25._dirty = True
            logger.info("Indexed %d web search results for: %s", len(ids), query[:60])

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _ensure_bm25(self):
        """Lazily build BM25 index from all ChromaDB documents."""
        if not _bm25._dirty:
            return
        try:
            all_data = self.collection.get(include=["documents"])
            docs = all_data.get("documents", []) or []
            if docs:
                _bm25.build(docs)
                logger.debug("BM25 index built: %d documents", len(docs))
        except Exception as e:
            logger.warning("BM25 index build failed: %s", e)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant entries with hybrid (embedding + BM25) scoring.

        Applies query rewrite + retrieval cache automatically.

        Args:
            query: User question text.
            k: Number of results to return.
            content_type: Optional filter — "text", "image", "table", or None (all).

        Returns:
            List of dicts with keys: content, source, type, chunk_index, indexed_at,
            distance, (image_path if type=image).
        """
        # 1. Check retrieval cache first (key includes content_type to avoid
        #    mixing results from different type filters)
        cache_key = f"{query}|{content_type or 'all'}"
        cached = retrieval_cache.get(cache_key)
        if cached is not None:
            logger.debug("Retrieval cache hit: %s", cache_key[:60])
            return cached

        # 2. Apply query rewrite (expand abbreviations)
        rewritten = rewrite_query(query)
        final_query = rewritten if rewritten != query else query
        if final_query != query:
            logger.debug("Query rewritten: %s → %s", query[:40], final_query[:60])

        # 3. Build BM25 index lazily
        self._ensure_bm25()

        # 4. Query ChromaDB — get extra candidates for hybrid reranking
        where = None
        if content_type:
            where = {"type": content_type}

        # Get more candidates so BM25 has room to re-rank
        hybrid_k = max(k * 2, 8)
        results = self.collection.query(
            query_texts=[final_query],
            n_results=hybrid_k,
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

        for idx, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
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

        # 5. Hybrid re-rank: fuse embedding similarity with BM25 scores (no CrossEncoder — adds latency for marginal gain)
        if len(entries) > k and not _bm25._dirty:
            bm25_scores = _bm25.scores(final_query, range(len(documents)))
            # Normalize BM25 scores to 0-1 range
            bm25_vals = list(bm25_scores.values())
            bm25_min = min(bm25_vals) if bm25_vals else 0
            bm25_max = max(bm25_vals) if bm25_vals else 1
            bm25_range = bm25_max - bm25_min if bm25_max > bm25_min else 1

            for i, entry in enumerate(entries):
                bm25_norm = (bm25_scores.get(i, 0) - bm25_min) / bm25_range
                # Fuse: 70% embedding + 30% BM25
                entry["similarity"] = 0.7 * entry.get("similarity", 0) + 0.3 * bm25_norm

            # Sort by hybrid score and keep top-k
            entries.sort(key=lambda e: e["similarity"], reverse=True)
            entries = entries[:k]

        # 5.5 Keyword boost: if any query term literally appears in the document,
        #     set a minimum similarity floor of 0.55.  This prevents the gate from
        #     skipping documents that contain the exact keyword (common with short
        #     queries like "rag是什么" where embedding similarity is naturally low).
        import re as _re
        _query_lower = final_query.lower()
        # Strip parens/brackets and split into clean tokens
        _clean_tokens = set(_re.findall(r'[\w一-鿿]+', _query_lower))
        # Also add the original query terms (before any expansion suffix)
        _paren_start = _query_lower.find("(")
        if _paren_start > 0:
            _clean_tokens.update(_re.findall(r'[\w一-鿿]+', _query_lower[:_paren_start]))
        for entry in entries:
            doc_lower = entry.get("content", "").lower()
            matching_terms = [t for t in _clean_tokens if len(t) >= 2 and t in doc_lower]
            if matching_terms:
                if entry["similarity"] < 0.55:
                    entry["similarity"] = 0.55

        # 6. Cache the result
        retrieval_cache.set(cache_key, entries)
        logger.info(
            "RAG retrieve: query='%s' type=%s → %d results (top sim=%.4f, types=%s)",
            query[:60], content_type or 'all', len(entries),
            entries[0]['similarity'] if entries else 0,
            [e['type'] for e in entries],
        )
        return entries

    @staticmethod
    def format_chunks_as_context(entries: list) -> str:
        """Format raw retrieved chunks into a context string for prompt injection.

        Deduplicates near-identical chunks before formatting.
        Can be called directly with retrieve() output to avoid re-querying ChromaDB.
        """
        if not entries:
            return ""

        # Dedup: skip chunks that are largely redundant with a higher-similarity neighbor
        deduped = []
        for e in entries:
            content = e.get("content", "")
            is_dup = False
            for existing in deduped:
                existing_content = existing.get("content", "")
                # Check if one is a prefix/substring of the other (common at chunk boundaries)
                if content.startswith(existing_content) or existing_content.startswith(content):
                    is_dup = True
                    break
                # Check if first 80 chars are identical
                if content[:80] == existing_content[:80]:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(e)

        from urllib.parse import quote
        context = "以下是与问题相关的讲座内容：\n\n"
        context += (
            "【图片路径规则】只使用链接中已提供 `![](/images/...)` 的图片路径。"
            "无论后续提到什么文件名，都不要自己猜测图片路径。"
            "特别禁止使用 `幻灯片1.png`、`Slide1.png`、`图片1.png` 等猜测的文件名。\n\n"
        )
        text_idx = 1
        for entry in deduped:
            tag = {"text": "文本", "image": "图片", "table": "表格"}.get(
                entry["type"], "内容"
            )
            similarity = entry["similarity"]
            source_name = Path(entry.get("source", "")).name

            # Try to resolve image file
            img_reference = ""
            if entry.get("image_path"):
                img_path = Path(entry["image_path"])
                if not img_path.exists():
                    img_filename = entry.get("image_filename", "")
                    if img_filename:
                        candidate = self.images_directory / img_filename
                        if candidate.exists():
                            img_path = candidate
                if img_path.exists():
                    safe_name = quote(img_path.name)
                    img_reference = f"\n\n![](/images/{safe_name})"

            if entry.get("type") == "image" and not img_reference:
                # No valid image file on disk — hide source to prevent LLM guesswork
                context += (
                    f"[{text_idx}] {tag}（图片文件缺失，仅供参考描述）\n"
                    f"{entry['content']}\n\n"
                )
            else:
                context += (
                    f"[{text_idx}] {tag} — 来源：{source_name} "
                    f"(相关度：{similarity:.2f})\n"
                )
                context += f"{entry['content']}"
                if img_reference:
                    context += img_reference
                context += "\n\n"
            text_idx += 1

        img_ref_count = context.count('![](/images/')
        if img_ref_count > 0:
            logger.info("format_chunks_as_context: generated %d image refs", img_ref_count)
        else:
            logger.info("format_chunks_as_context: NO image refs in output (entries=%d)", len(deduped))
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
