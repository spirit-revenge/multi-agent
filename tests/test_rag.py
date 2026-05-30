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
        """Disable module-level caches/reranker before each test."""
        from tools.rag_store import retrieval_cache, _reranker
        retrieval_cache.clear()
        _reranker._available = False

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
        from tools.rag_store import LectureVectorStore, retrieval_cache, _reranker
        retrieval_cache.clear()
        _reranker._available = False  # skip model download in tests

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

        # Verify query was called with hybrid_k = max(k*4, 12) = 12
        store.collection.query.assert_called_with(
            query_texts=["test image query"],
            n_results=12,
            where={"type": "image"},
        )

        # Cleanup
        shutil.rmtree(store_dir, ignore_errors=True)

    def test_get_context_for_query(self):
        from tools.rag_store import LectureVectorStore
        store, store_dir = self._make_store()

        store.collection.query.return_value = {
            "documents": [["这是文本。", "| A | B |"]],
            "metadatas": [[{"type": "text", "source": "a.pdf", "indexed_at": "2026-01-01"},
                          {"type": "table", "source": "a.pdf", "indexed_at": "2026-01-01"}]],
            "distances": [[0.1, 0.2]],
            "ids": [["id1", "id2"]],
        }

        ctx = store.get_context_for_query("test", k=2)
        assert "这是文本" in ctx
        assert "| A | B |" in ctx
        assert "📝" in ctx  # text icon
        assert "📊" in ctx  # table icon

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


@pytest.fixture(autouse=True)
def cleanup_temp():
    """Clean up temp directories after each test in this file."""
    yield


# Need shutil for cleanup
import shutil
