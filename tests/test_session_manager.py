import tempfile
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
