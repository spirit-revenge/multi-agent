import tempfile
import json
from pathlib import Path
from tools.session_manager import ConversationSessionManager, SessionInfo


class TestSessionManager:
    """Test the multi-session manager module."""

    def _make_manager(self):
        tmp_dir = Path(tempfile.mkdtemp())
        legacy = tmp_dir / "session.json"
        mgr = ConversationSessionManager(legacy_session_file=str(legacy))
        return mgr, tmp_dir

    def test_create_session_default_name(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session()
        assert path.exists()
        assert path.suffix == ".json"
        data = __import__("json").loads(path.read_text(encoding="utf-8"))
        assert "messages" in data
        assert data["messages"] == []

    def test_create_session_named(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session("my-lecture-notes")
        assert "my-lecture-notes" in str(path)

    def test_list_sessions_empty(self):
        mgr, tmp = self._make_manager()
        sessions = mgr.list_sessions()
        assert sessions == []

    def test_list_sessions(self):
        mgr, tmp = self._make_manager()
        mgr.create_session("test1")
        mgr.create_session("test2")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_with_legacy(self):
        mgr, tmp = self._make_manager()
        mgr.legacy_session_file.write_text(
            '{"messages": [{"role": "user", "content": "old"}]}',
            encoding="utf-8",
        )
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].is_legacy is True
        assert sessions[0].name == "default"

    def test_session_label(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session("hello-world")
        label = mgr.session_label(path)
        assert label == "hello-world"

    def test_legacy_session_label(self):
        mgr, tmp = self._make_manager()
        label = mgr.session_label(mgr.legacy_session_file)
        assert label == "default"

    def test_delete_session(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session("temp")
        assert path.exists()
        assert mgr.delete_session(path) is True
        assert not path.exists()

    def test_cannot_delete_legacy(self):
        mgr, tmp = self._make_manager()
        assert mgr.delete_session(mgr.legacy_session_file) is False

    def test_delete_nonexistent(self):
        mgr, tmp = self._make_manager()
        assert mgr.delete_session(Path("/nonexistent/path.json")) is False

    def test_search_all_sessions_finds_match(self):
        mgr, tmp = self._make_manager()
        path1 = mgr.create_session("test1")
        path1.write_text(
            json.dumps({"messages": [
                {"role": "user", "content": "什么是 BERT？"},
                {"role": "assistant", "content": "BERT 是..."},
            ]}),
            encoding="utf-8",
        )
        path2 = mgr.create_session("test2")
        path2.write_text(
            json.dumps({"messages": [
                {"role": "user", "content": "解释 Transformer"},
            ]}),
            encoding="utf-8",
        )
        results = mgr.search_all_sessions("BERT")
        assert len(results) == 2
        assert results[0]["session"] in ("test1", "test2")
        assert "session_file" in results[0]

    def test_search_all_sessions_case_insensitive(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session("test")
        path.write_text(
            json.dumps({"messages": [
                {"role": "user", "content": "Hello World"},
            ]}),
            encoding="utf-8",
        )
        results = mgr.search_all_sessions("hello")
        assert len(results) == 1

    def test_search_all_sessions_no_match(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session("test")
        path.write_text(
            json.dumps({"messages": [
                {"role": "user", "content": "BERT"},
            ]}),
            encoding="utf-8",
        )
        results = mgr.search_all_sessions("Transformer")
        assert len(results) == 0

    def test_search_all_sessions_empty(self):
        mgr, tmp = self._make_manager()
        results = mgr.search_all_sessions("anything")
        assert len(results) == 0

    def test_search_all_sessions_has_required_fields(self):
        mgr, tmp = self._make_manager()
        path = mgr.create_session("test")
        path.write_text(
            json.dumps({"messages": [
                {"role": "user", "content": "test message", "timestamp": "2026-01-01T00:00:00"},
            ]}),
            encoding="utf-8",
        )
        results = mgr.search_all_sessions("test")
        assert len(results) == 1
        r = results[0]
        assert r["session"] == "test"
        assert r["role"] == "user"
        assert r["content"] == "test message"
        assert r["index"] == 0
        assert r["timestamp"] == "2026-01-01T00:00:00"
        assert r["session_file"] == str(path)
