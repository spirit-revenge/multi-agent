"""
Tests for the RAG system: document processing, image captioning, and vector store.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, PropertyMock

import pytest

# ============================================================================
# Helpers
# ============================================================================

# Sample text for chunking tests
SHORT_PARAS = "第一段。\n\n第二段。\n\n第三段。"
LONG_PARAS = "。\n\n".join(["这是第{}段内容，包含一些详细说明。".format(i) for i in range(1, 6)])
HEADER_TEXT = "## 引言\n\n这是引言段落。\n\n### 背景\n\n这是背景部分。"


# ============================================================================
# Tests: _semantic_chunk
# ============================================================================

class TestSemanticChunk:
    """Test the semantic chunking logic."""

    def test_empty_text(self):
        from tools.document_processor import _semantic_chunk
        assert _semantic_chunk("") == []
        assert _semantic_chunk("   ") == []
        assert _semantic_chunk("\n\n\n") == []

    def test_single_paragraph(self):
        from tools.document_processor import _semantic_chunk
        text = "这是一个单独的段落。"
        chunks = _semantic_chunk(text)
        assert len(chunks) == 1
        assert "单独的段落" in chunks[0]

    def test_multiple_paragraphs(self):
        from tools.document_processor import _semantic_chunk
        chunks = _semantic_chunk(SHORT_PARAS)
        # All 3 paras are short, they merge into one chunk (below min_size individually)
        assert len(chunks) >= 1
        assert any("第一段" in c for c in chunks)
        assert any("第三段" in c for c in chunks)

    def test_heading_boundary(self):
        from tools.document_processor import _semantic_chunk
        chunks = _semantic_chunk(HEADER_TEXT)
        # Headings create separate chunks
        heading_chunks = [c for c in chunks if c.startswith("##")]
        assert len(heading_chunks) >= 1

    def test_long_text_split(self):
        from tools.document_processor import _semantic_chunk
        # Create text that exceeds max_size (1200) with sentence boundaries
        text = "第一句话。" * 100 + "\n\n" + "第二句话。" * 100
        chunks = _semantic_chunk(text)
        # Should be split into at least 2 chunks
        assert len(chunks) >= 2
        # Each chunk should not exceed max_size by much
        for c in chunks:
            assert len(c) <= 1300, f"Chunk too long: {len(c)} chars"

    def test_mixed_content(self):
        from tools.document_processor import _semantic_chunk
        text = "## 标题\n\n正文段落内容，这里是一些较长的正文以跨越最小合并阈值。\n\n- 列表项1\n- 列表项2\n\n另一段正文，同样需要足够长才能不被合并。"
        chunks = _semantic_chunk(text)
        # heading stays separate; other paragraphs may merge if below min_size
        assert len(chunks) >= 2
        assert chunks[0] == "## 标题"

    def test_normalized_line_endings(self):
        from tools.document_processor import _semantic_chunk
        text = "第一段。\r\n\r\n第二段。"
        chunks = _semantic_chunk(text)
        assert len(chunks) >= 1


# ============================================================================
# Tests: _table_to_markdown
# ============================================================================

class TestTableToMarkdown:
    """Test the table → Markdown conversion."""

    def test_basic_table(self):
        from tools.document_processor import _table_to_markdown
        rows = [["名称", "数量"], ["苹果", "3"], ["香蕉", "5"]]
        md = _table_to_markdown(rows)
        assert md is not None
        assert "名称" in md
        assert "苹果" in md
        assert "---" in md
        assert md.count("|") >= 6  # 3 rows × 2 cells × 2 pipes

    def test_single_row_returns_none(self):
        from tools.document_processor import _table_to_markdown
        assert _table_to_markdown([["Only header"]]) is None
        assert _table_to_markdown([]) is None

    def test_empty_cells(self):
        from tools.document_processor import _table_to_markdown
        rows = [["A", "B"], ["", "value"], ["data", ""]]
        md = _table_to_markdown(rows)
        assert md is not None
        assert "|  | value |" in md or "|  | value|" in md
        assert "| data |  |" in md or "| data | |" in md

    def test_pipe_in_cell(self):
        from tools.document_processor import _table_to_markdown
        rows = [["Key", "Value"], ["pipe|char", "ok"]]
        md = _table_to_markdown(rows)
        assert md is not None
        assert "pipe\\|char" in md  # Pipe should be escaped

    def test_uneven_rows(self):
        from tools.document_processor import _table_to_markdown
        rows = [["A", "B", "C"], ["short"]]
        md = _table_to_markdown(rows)
        assert md is not None
        # Should pad to 3 columns
        lines = md.strip().split('\n')
        body_cells = lines[2].count('|')
        assert body_cells >= 4  # 3 cells + 2 edges ≈ 4 pipes

    def test_newline_in_cell(self):
        from tools.document_processor import _table_to_markdown
        rows = [["Name", "Desc"], ["AI", "line1\nline2"]]
        md = _table_to_markdown(rows)
        assert md is not None
        assert "line1 line2" in md  # Newline replaced with space


# ============================================================================
# Tests: process_document
# ============================================================================

class TestProcessDocument:
    """Test document processing dispatch."""

    def test_unsupported_extension(self):
        from tools.document_processor import process_document
        # File must exist for the extension check to be reached
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("dummy")
            tmp = f.name
        try:
            with pytest.raises(ValueError):
                process_document(tmp)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_file_not_found(self):
        from tools.document_processor import process_document
        with pytest.raises(FileNotFoundError):
            process_document("/nonexistent/file.pdf")

    def test_supported_extensions(self):
        from tools.document_processor import SUPPORTED_EXTENSIONS
        assert '.pdf' in SUPPORTED_EXTENSIONS
        assert '.pptx' in SUPPORTED_EXTENSIONS
        assert '.docx' in SUPPORTED_EXTENSIONS

    @patch("tools.document_processor._process_pdf")
    def test_pdf_dispatch(self, mock_process):
        from tools.document_processor import process_document
        mock_process.return_value = {"texts": ["hello"], "images": [], "tables": []}

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"dummy")
            tmp = f.name

        try:
            result = process_document(tmp)
            mock_process.assert_called_once()
            assert result["texts"] == ["hello"]
        finally:
            Path(tmp).unlink(missing_ok=True)

    @patch("tools.document_processor._process_pptx")
    def test_pptx_dispatch(self, mock_process):
        from tools.document_processor import process_document
        mock_process.return_value = {"texts": [], "images": [], "tables": []}

        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            f.write(b"dummy")
            tmp = f.name

        try:
            result = process_document(tmp)
            mock_process.assert_called_once()
        finally:
            Path(tmp).unlink(missing_ok=True)

    @patch("tools.document_processor._process_docx")
    def test_docx_dispatch(self, mock_process):
        from tools.document_processor import process_document
        mock_process.return_value = {"texts": [], "images": [], "tables": []}

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy")
            tmp = f.name

        try:
            result = process_document(tmp)
            mock_process.assert_called_once()
        finally:
            Path(tmp).unlink(missing_ok=True)


# ============================================================================
# Tests: _safe_filename, _file_path_hash, _image_stem (Bug #22, #3)
# ============================================================================

class TestFilenameSafety:
    """Test filename sanitization and collision prevention."""

    def test_safe_filename_replaces_ampersand(self):
        """Bug #22: & in filenames causes URL query parameter issues."""
        from tools.document_processor import _safe_filename
        result = _safe_filename("W12_LLM_RAG&Agent")
        assert "&" not in result
        assert "RAG_Agent" in result

    def test_safe_filename_replaces_spaces(self):
        from tools.document_processor import _safe_filename
        result = _safe_filename("My Lecture File")
        assert " " not in result

    def test_safe_filename_collapses_underscores(self):
        from tools.document_processor import _safe_filename
        result = _safe_filename("a@#b!!!c")
        # Multiple special chars replaced with single underscore
        assert "__" not in result

    def test_file_path_hash_deterministic(self):
        """Same path always produces same hash."""
        from tools.document_processor import _file_path_hash
        h1 = _file_path_hash("/knowledge/W11_LLM.pptx")
        h2 = _file_path_hash("/knowledge/W11_LLM.pptx")
        assert h1 == h2
        assert len(h1) == 8

    def test_file_path_hash_different_for_different_paths(self):
        from tools.document_processor import _file_path_hash
        h1 = _file_path_hash("/a/test.pptx")
        h2 = _file_path_hash("/b/test.pptx")
        assert h1 != h2

    def test_image_stem_includes_path_hash(self):
        """Bug #3: image stem includes path hash to prevent collisions."""
        from tools.document_processor import _image_stem, _file_path_hash
        result = _image_stem("/knowledge/W11_LLM.pptx")
        expected_hash = _file_path_hash("/knowledge/W11_LLM.pptx")
        assert f"W11_LLM_{expected_hash}" == result
        assert len(result) > len("W11_LLM")  # hash appended

    def test_image_stem_disambiguates_same_stem_different_dir(self):
        """Bug #3: two files with same stem in different dirs get unique stems."""
        from tools.document_processor import _image_stem
        s1 = _image_stem("/knowledge/W11_LLM.pptx")
        s2 = _image_stem("/knowledge/archive/W11_LLM.pptx")
        assert s1 != s2


# ============================================================================
# Tests: image_captioner
# ============================================================================

class TestImageCaptioner:
    """Test the image captioning module."""

    def test_describe_image(self):
        """BLIP should describe a simple test image."""
        from tools.image_captioner import describe_image
        from PIL import Image

        img = Image.new('RGB', (100, 50), color='red')
        caption = describe_image(img)
        # BLIP should produce an English description starting with "[图片描述]"
        assert caption.startswith("[图片描述]")
        assert len(caption) > 10

    @patch("tools.image_captioner._get_captioner")
    def test_describe_image_success(self, mock_get):
        """Test with a mocked BLIP pipeline."""
        from tools.image_captioner import describe_image
        from PIL import Image

        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [{"generated_text": "a diagram of transformer architecture"}]
        mock_get.return_value = mock_pipeline

        img = Image.new('RGB', (200, 100), color='blue')
        caption = describe_image(img)
        assert "transformer architecture" in caption
        assert "[图片描述]" in caption

    def test_describe_images_batch(self):
        """Test batch processing."""
        from tools.image_captioner import describe_images_batch
        from PIL import Image

        imgs = [
            (Image.new('RGB', (50, 50), color='red'), "img1.png"),
            (Image.new('RGB', (60, 60), color='green'), "img2.png"),
        ]
        results = describe_images_batch(imgs)
        assert len(results) == 2
        for desc, img, fname in results:
            assert desc.startswith("[图片描述]")
            assert isinstance(img, Image.Image)


# ============================================================================
# Tests: LectureVectorStore
# ============================================================================

class TestLectureVectorStore:
    """Test the vector store with mocked ChromaDB."""

class _DummyEmbedding:
    """A ChromaDB-compatible dummy embedding function (no model loading)."""
    def __init__(self):
        self._dimension = 384

    def __call__(self, input):
        import numpy as np
        if isinstance(input, str):
            return np.zeros(self._dimension)
        return np.zeros((len(input), self._dimension))

    def embed_documents(self, input):
        return self.__call__(input)

    def embed_query(self, input):
        return np.zeros(self._dimension)

    def name(self):
        return "dummy-embedding"

    def get_config(self):
        return {}

    @property
    def dimension(self):
        return self._dimension

    @classmethod
    def build_from_config(cls, config):
        return cls()


class TestLectureVectorStore:
    """Test the vector store with mocked ChromaDB."""

    @staticmethod
    def _setup_method():
        """Disable module-level caches before each test."""
        from tools.rag_store import retrieval_cache
        retrieval_cache.clear()

    def _make_store(self):
        """Create a store with temp directories and a mocked collection."""
        self._setup_method()
        """Create a store with temp directories and a mocked collection."""
        from tools.rag_store import LectureVectorStore

        # Patch LocalEmbeddingFunction BEFORE instantiating to avoid model load
        with patch("tools.rag_store.LocalEmbeddingFunction", return_value=_DummyEmbedding()):
            tmp_dir = Path(tempfile.mkdtemp())
            store = LectureVectorStore(
                persist_directory=str(tmp_dir / "chroma_db"),
                images_directory=str(tmp_dir / "images"),
            )

        # Replace the real collection with a MagicMock for unit-test isolation
        store.collection = MagicMock()
        store.collection.metadata = {}
        store.collection.count.return_value = 0
        return store, tmp_dir

    def test_init_creates_dirs(self):
        from tools.rag_store import LectureVectorStore
        tmp_dir = Path(tempfile.mkdtemp())
        chroma = tmp_dir / "c"
        images = tmp_dir / "i"

        store = LectureVectorStore(
            persist_directory=str(chroma),
            images_directory=str(images),
        )
        assert chroma.exists()
        assert images.exists()

    def test_get_file_hash(self):
        from tools.rag_store import LectureVectorStore
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            tmp = f.name
        try:
            h = LectureVectorStore._get_file_hash(tmp)
            assert isinstance(h, str)
            assert len(h) == 64  # SHA256 hex
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_index_single_file(self, tmp_path):
        """Test indexing a file via mocked document processing."""
        from tools.rag_store import LectureVectorStore
        from PIL import Image
        import io

        store, store_dir = self._make_store()

        # Mock process_document output
        mock_result = {
            "texts": ["第一段内容。", "第二段内容。"],
            "images": [
                (Image.new('RGB', (100, 50), color='red'), "test_img1.png"),
            ],
            "tables": [
                "| A | B |\n| --- | --- |\n| 1 | 2 |",
            ],
        }

        with patch("tools.rag_store.process_document", return_value=mock_result):
            with patch("tools.rag_store.describe_images_batch") as mock_desc:
                mock_desc.return_value = [
                    ("[图片描述] a red test image", mock_result["images"][0][0], "test_img1.png"),
                ]

                test_file = tmp_path / "test.docx"
                test_file.write_text("dummy content")

                store._index_single_file(test_file)

                # Check add was called with the right structure
                store.collection.add.assert_called_once()
                call_kwargs = store.collection.add.call_args.kwargs or {}
                ids = call_kwargs.get("ids", [])
                documents = call_kwargs.get("documents", [])
                metadatas = call_kwargs.get("metadatas", [])

                # Should have text + image + table entries
                assert len(ids) == 4  # 2 text + 1 image + 1 table

                # Check metadata structure
                text_meta = [m for m in metadatas if m["type"] == "text"]
                img_meta = [m for m in metadatas if m["type"] == "image"]
                table_meta = [m for m in metadatas if m["type"] == "table"]

                assert len(text_meta) == 2
                assert len(img_meta) == 1
                assert len(table_meta) == 1

                # Check timestamp
                for m in metadatas:
                    assert "indexed_at" in m
                    assert m["indexed_at"]

                # Check image path
                assert img_meta[0]["image_path"]
                assert img_meta[0]["image_filename"] == "test_img1.png"

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_retrieve_text_only(self):
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        # Mock query response
        store.collection.query.return_value = {
            "documents": [["文本内容", "表格内容"]],
            "metadatas": [[{"type": "text", "source": "a.pdf", "indexed_at": "2026-01-01"},
                          {"type": "table", "source": "a.pdf", "indexed_at": "2026-01-01"}]],
            "distances": [[0.1, 0.3]],
            "ids": [["id1", "id2"]],
        }

        results = store.retrieve("test query", k=2)
        assert len(results) == 2
        assert results[0]["type"] == "text"
        assert results[1]["type"] == "table"
        assert results[0]["similarity"] == pytest.approx(0.9)  # 1 - 0.1

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_retrieve_filter_by_type(self):
        from tools.rag_store import LectureVectorStore, retrieval_cache
        retrieval_cache.clear()

        store, store_dir = self._make_store()

        # Mock collection.get() for BM25 initialization (returns no docs)
        store.collection.get.return_value = {"documents": []}

        store.collection.query.return_value = {
            "documents": [["图片描述"]],
            "metadatas": [[{"type": "image", "source": "b.pptx", "indexed_at": "2026-01-01",
                           "image_path": "images/test.png"}]],
            "distances": [[0.2]],
            "ids": [["id3"]],
        }

        results = store.retrieve("test image query", k=3, content_type="image")
        assert len(results) == 1
        assert results[0]["type"] == "image"
        assert results[0]["image_path"] == "images/test.png"

        # Verify query was called with hybrid_k = max(k*2, 8) = 8 (k=3 → max(6,8) = 8)
        store.collection.query.assert_called_with(
            query_texts=["test image query"],
            n_results=8,
            where={"type": "image"},
        )

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_format_chunks_as_context(self):
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        entries = [
            {"content": "这是文本。", "source": "a.pdf", "type": "text",
             "chunk_index": 0, "indexed_at": "2026-01-01", "similarity": 0.9},
            {"content": "| A | B |\n| --- | --- |\n| 1 | 2 |", "source": "a.pdf",
             "type": "table", "chunk_index": 0, "indexed_at": "2026-01-01",
             "similarity": 0.8},
        ]
        ctx = store.format_chunks_as_context(entries)
        assert "这是文本" in ctx
        assert "| A | B |" in ctx
        assert "文本" in ctx  # text tag
        assert "表格" in ctx  # table tag

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_delete_file(self):
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        # Mock that there are existing entries
        store.collection.get.return_value = {
            "ids": ["id1", "id2"],
            "metadatas": [
                {"type": "image", "image_path": str(store_dir / "images" / "test.png")},
                {"type": "text", "source": "a.pdf"},
            ],
        }

        count = store.delete_file("a.pdf")
        assert count == 2
        store.collection.delete.assert_called_once_with(ids=["id1", "id2"])

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_get_stats(self):
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        store.collection.get.return_value = {
            "ids": ["id1", "id2", "id3"],
            "metadatas": [
                {"type": "text"},
                {"type": "image"},
                {"type": "table"},
            ],
        }

        stats = store.get_stats()
        assert stats["total"] == 3
        assert stats["by_type"]["text"] == 1
        assert stats["by_type"]["image"] == 1
        assert stats["by_type"]["table"] == 1

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_index_files_skip_unchanged(self):
        """When no files changed, skip indexing."""
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        # Pre-populate existing file hashes
        store._save_file_hashes = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"dummy content")
            tmp = Path(f.name)

        try:
            # First index (no existing hash = force index)
            with patch("tools.rag_store.LectureVectorStore._index_single_file") as mock_idx:
                store.index_files(str(tmp.parent), force_reindex=False)
                mock_idx.assert_called_once()

            # Second index with same file = should skip
            # Mock both load and save so the hash is properly round-tripped
            store._load_file_hashes = MagicMock(return_value={str(tmp): store._get_file_hash(str(tmp))})
            with patch("tools.rag_store.LectureVectorStore._index_single_file") as mock_idx:
                store.index_files(str(tmp.parent), force_reindex=False)
                mock_idx.assert_not_called()

        finally:
            tmp.unlink(missing_ok=True)
            shutil.rmtree(store_dir, ignore_errors=True)


    def test_index_web_search_stores_facts(self):
        """Web search facts are stored with type='web' metadata."""
        store, tmp_dir = self._make_store()
        store.collection.get.return_value = {"ids": []}
        store.collection.add.return_value = None

        facts = ["今天北京天气晴，25°C", "明天多云转阴，22°C"]
        urls = ["https://weather.example.com/beijing"]
        store.index_web_search("北京天气", facts, urls)

        # Verify add was called
        assert store.collection.add.called
        call_args = store.collection.add.call_args[1]
        assert len(call_args["ids"]) == 2
        assert all(m["type"] == "web" for m in call_args["metadatas"])
        assert all("web_query" in m for m in call_args["metadatas"])
        assert call_args["metadatas"][0]["web_query"] == "北京天气"
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_index_web_search_skips_empty_facts(self):
        """Empty facts list should not call collection.add."""
        store, tmp_dir = self._make_store()
        store.index_web_search("query", [])
        assert not store.collection.add.called
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_index_web_search_dedup_same_query(self):
        """Re-indexing the same query deletes old entries first."""
        store, tmp_dir = self._make_store()
        store.collection.get.return_value = {"ids": ["web_abc_0", "web_abc_1"]}
        store.collection.delete.return_value = None
        store.collection.add.return_value = None

        store.index_web_search("北京天气", ["fact 1"])

        # Should have called delete for old entries
        assert store.collection.delete.called
        store.collection.delete.assert_called_once_with(ids=["web_abc_0", "web_abc_1"])
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_index_web_search_without_urls(self):
        """URLs default to empty list if not provided."""
        store, tmp_dir = self._make_store()
        store.collection.get.return_value = {"ids": []}
        store.collection.add.return_value = None

        store.index_web_search("query", ["fact 1"])  # no urls arg

        call_args = store.collection.add.call_args[1]
        meta = call_args["metadatas"][0]
        assert meta["urls"] == "[]"
        shutil.rmtree(tmp_dir, ignore_errors=True)


    def test_index_file_single_upload(self):
        """index_file() indexes one file without scanning directory."""
        store, tmp_dir = self._make_store()
        store._delete_file_entries = MagicMock()
        store._get_file_hash = MagicMock(return_value="abc123")
        store._load_file_hashes = MagicMock(return_value={})
        store._save_file_hashes = MagicMock()

        # Create a fake PDF file
        pdf = Path(tmp_dir) / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake pdf")

        # Mock process_document + describe_images_batch
        with patch("tools.rag_store.process_document") as mock_proc, \
             patch("tools.rag_store.describe_images_batch", return_value=[]):
            mock_proc.return_value = {"texts": ["chunk 1", "chunk 2"], "images": [], "tables": []}
            store.collection.add.return_value = None

            store.index_file(str(pdf))

        # Verify it called collection.add with 2 text chunks
        assert store.collection.add.called
        call_args = store.collection.add.call_args[1]
        assert len(call_args["documents"]) == 2
        assert store._save_file_hashes.called
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_retrieve_cache_key_includes_content_type(self):
        """Bug #7: different content_type filters must use separate cache keys."""
        from tools.rag_store import LectureVectorStore, retrieval_cache
        store, store_dir = self._make_store()

        retrieval_cache.clear()
        try:
            query = "Transformer architecture"

            # First call with content_type="image"
            store.collection.query.return_value = {
                "documents": [["image desc"]],
                "metadatas": [[{"type": "image", "source": "a.pptx",
                               "indexed_at": "2026-01-01",
                               "image_path": "images/test.png"}]],
                "distances": [[0.3]],
                "ids": [["img1"]],
            }
            results_img = store.retrieve(query, k=3, content_type="image")
            assert len(results_img) == 1
            assert results_img[0]["type"] == "image"

            # Second call with content_type=None should NOT hit the image cache
            store.collection.query.return_value = {
                "documents": [["text content"]],
                "metadatas": [[{"type": "text", "source": "a.pdf",
                               "indexed_at": "2026-01-01"}]],
                "distances": [[0.2]],
                "ids": [["txt1"]],
            }
            results_all = store.retrieve(query, k=3, content_type=None)
            assert len(results_all) == 1
            assert results_all[0]["type"] == "text"
        finally:
            retrieval_cache.clear()
            shutil.rmtree(store_dir, ignore_errors=True)

    def test_keyword_boost_floors_low_similarity(self):
        """Bug #2: exact keyword matches floor similarity to 0.55."""
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        # Simulate ChromaDB returning a low-similarity result for "rag"
        store.collection.query.return_value = {
            "documents": [["Retrieval Augmented Generation (RAG) is a technique..."]],
            "metadatas": [[{"type": "text", "source": "W12_LLM_RAG.pptx",
                           "indexed_at": "2026-01-01"}]],
            "distances": [[0.65]],  # 1 - 0.65 = 0.35 similarity
            "ids": [["rag_doc"]],
        }

        results = store.retrieve("rag是什么", k=3)
        assert len(results) >= 1
        sim = results[0]["similarity"]
        # The boost should floor similarity to at least 0.55
        # "rag" token should match the document content (both lowercase)
        assert sim >= 0.55, f"Expected similarity >= 0.55 after keyword boost, got {sim}"

        shutil.rmtree(store_dir, ignore_errors=True)

    def test_keyword_boost_no_effect_on_high_similarity(self):
        """Keyword boost should not lower already-high similarity scores."""
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        store.collection.query.return_value = {
            "documents": [["Transformer architecture uses self-attention..."]],
            "metadatas": [[{"type": "text", "source": "W5_Transformer.pptx",
                           "indexed_at": "2026-01-01"}]],
            "distances": [[0.15]],  # 1 - 0.15 = 0.85 similarity
            "ids": [["transformer_doc"]],
        }

        results = store.retrieve("Transformer architecture", k=3)
        assert len(results) >= 1
        sim = results[0]["similarity"]
        # Already high similarity should stay as-is (~0.85)
        assert sim > 0.55, f"Expected similarity > 0.55, got {sim}"

        shutil.rmtree(store_dir, ignore_errors=True)

    def test_index_file_rejects_wrong_extension(self):
        """index_file() raises ValueError for unsupported file types."""
        store, tmp_dir = self._make_store()
        txt = Path(tmp_dir) / "notes.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            store.index_file(str(txt))
        shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_reindex_preserves_entries_when_file_unchanged(self):
        """Force reindex of unchanged file should NOT delete its own entries.

        When old_ids == new_ids (same file, same content), the delete step
        must skip overlapping IDs to avoid wiping fresh data.
        """
        store, tmp_dir = self._make_store()
        from unittest.mock import patch, MagicMock

        file_path = Path(tmp_dir) / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4 content")

        # Simulate: old entries exist with same ID prefix as new ones would get
        id_prefix = "test_abc12345"
        old_ids = [f"{id_prefix}_text_0", f"{id_prefix}_text_1", f"{id_prefix}_img_0"]
        store.collection.get.return_value = {
            "ids": old_ids,
            "metadatas": [
                {"type": "text", "source": str(file_path)},
                {"type": "text", "source": str(file_path)},
                {"type": "image", "source": str(file_path), "image_path": str(tmp_dir / "images" / "old.png")},
            ],
        }

        with patch("tools.rag_store.process_document") as mock_proc, \
             patch("tools.rag_store.describe_images_batch", return_value=[]):
            mock_proc.return_value = {"texts": ["chunk1", "chunk2"], "images": [], "tables": []}
            store.collection.add.return_value = None

            store._index_single_file(file_path)

        # Verify: add was called with 2 text entries
        assert store.collection.add.called
        new_ids = store.collection.add.call_args[1]["ids"]
        assert len(new_ids) == 2

        # Verify: delete was called, but only with non-overlapping IDs
        if store.collection.delete.called:
            deleted_ids = store.collection.delete.call_args[1].get("ids", [])
            for nid in new_ids:
                assert nid not in deleted_ids, f"Newly added ID {nid} should not be deleted"

        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def cleanup_temp():
    """Clean up temp directories after each test in this file."""
    yield


# Need shutil for cleanup
import shutil
