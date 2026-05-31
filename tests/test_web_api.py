import os
import tempfile
from pathlib import Path
import pytest

# Set required env vars before importing web_ui
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-for-testing-only")


@pytest.fixture
def client():
    """Create a Flask test client with temporary directories."""
    import web_ui

    web_ui.app.config["TESTING"] = True

    # Redirect data dirs to temp
    tmp = Path(tempfile.mkdtemp())
    (tmp / "conversations" / "sessions").mkdir(parents=True)
    (tmp / "cache").mkdir()
    (tmp / "output").mkdir()

    # Point session manager to temp dir
    web_ui.session_manager.legacy_session_file = tmp / "conversations" / "session.json"
    web_ui.session_manager.sessions_dir = tmp / "conversations" / "sessions"
    web_ui.answer_cache.cache_file = tmp / "cache" / "answer_cache.json"
    web_ui.answer_cache.cache = []

    with web_ui.app.test_client() as c:
        with web_ui.app.app_context():
            yield c


class TestStatusAPI:
    """Test the /api/status endpoint."""

    def test_status_returns_success(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "status" in data
        assert "current_session" in data["status"]
        assert "message_count" in data["status"]


class TestSessionsAPI:
    """Test session management endpoints."""

    def test_list_sessions(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "sessions" in data

    def test_create_session(self, client):
        resp = client.post(
            "/api/sessions",
            json={"name": "test-session"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestCacheAPI:
    """Test cache management endpoints."""

    def test_get_cache(self, client):
        resp = client.get("/api/cache")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "stats" in data

    def test_clear_cache(self, client):
        resp = client.delete("/api/cache")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestHistoryAPI:
    """Test conversation history endpoints."""

    def test_get_history(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "history" in data

    def test_clear_history(self, client):
        resp = client.delete("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestChatTaskAPI:
    """Test the SSE task creation endpoint."""

    def test_get_task_id(self, client):
        resp = client.get("/api/chat/task")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "task_id" in data
        assert len(data["task_id"]) == 8


class TestChatValidation:
    """Test chat endpoint input validation."""

    def test_empty_message_rejected(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False


class TestHistorySearchAPI:
    """Test the history search endpoint."""

    def test_search_requires_query(self, client):
        resp = client.get("/api/history/search")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "搜索词" in data["error"]

    def test_search_empty_query(self, client):
        resp = client.get("/api/history/search?q=")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_search_returns_results(self, client):
        resp = client.get("/api/history/search?q=test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "results" in data
        assert "count" in data
        assert isinstance(data["results"], list)

    def test_search_with_all_flag(self, client):
        resp = client.get("/api/history/search?q=test&all=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "results" in data


class TestPageRoutes:
    """Test basic page routes."""

    def test_index_redirects(self, client):
        resp = client.get("/")
        assert resp.status_code in (200, 302)
