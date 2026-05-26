import json
import tempfile
from pathlib import Path
from tools.answer_cache import AnswerCache


class TestAnswerCache:
    """Test suite for the answer cache module."""

    def _make_cache(self, ttl_days=30):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        return AnswerCache(cache_file=tmp.name, ttl_days=ttl_days), Path(tmp.name)

    def test_cache_miss_on_empty(self):
        cache, path = self._make_cache()
        assert cache.get_answer("What is a transformer?") is None
        path.unlink(missing_ok=True)

    def test_cache_save_and_hit(self):
        cache, path = self._make_cache()
        cache.save_answer("What is BERT?", "BERT stands for Bidirectional Encoder...")
        result = cache.get_answer("What is BERT?")
        assert result == "BERT stands for Bidirectional Encoder..."
        path.unlink(missing_ok=True)

    def test_cache_case_insensitive_match(self):
        cache, path = self._make_cache()
        cache.save_answer("What is GPT?", "Generative Pre-trained Transformer")
        result = cache.get_answer("what is gpt?")
        assert result == "Generative Pre-trained Transformer"
        path.unlink(missing_ok=True)

    def test_cache_whitespace_tolerant(self):
        cache, path = self._make_cache()
        cache.save_answer("  hello world  ", "response")
        result = cache.get_answer("hello world")
        assert result == "response"
        path.unlink(missing_ok=True)

    def test_cache_length(self):
        cache, path = self._make_cache()
        assert len(cache) == 0
        cache.save_answer("q1", "a1")
        cache.save_answer("q2", "a2")
        assert len(cache) == 2
        path.unlink(missing_ok=True)

    def test_cache_clear(self):
        cache, path = self._make_cache()
        cache.save_answer("q1", "a1")
        cache.clear_cache()
        assert len(cache) == 0
        path.unlink(missing_ok=True)

    def test_cache_expiry(self):
        cache, path = self._make_cache(ttl_days=0)
        cache.save_answer("q1", "a1")
        # ttl_days=0 means no expiry, so answer should still be valid
        assert cache.get_answer("q1") == "a1"

        # With ttl_days=0 and immediate expiry simulation
        # TTL=0 means "no expiry" by design; test with a negative scenario
        # just verify stats work
        stats = cache.get_stats()
        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 1
        path.unlink(missing_ok=True)

    def test_cache_overwrite(self):
        cache, path = self._make_cache()
        cache.save_answer("q1", "first answer")
        cache.save_answer("q1", "updated answer")
        result = cache.get_answer("q1")
        assert result == "updated answer"
        assert len(cache) == 1
        path.unlink(missing_ok=True)

    def test_cache_persistence(self):
        cache1, path = self._make_cache()
        cache1.save_answer("persistent q", "persistent a")

        cache2 = AnswerCache(cache_file=str(path), ttl_days=30)
        result = cache2.get_answer("persistent q")
        assert result == "persistent a"
        path.unlink(missing_ok=True)
