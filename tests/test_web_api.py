import io
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote
import pytest
from unittest.mock import patch, MagicMock

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

    def test_chat_page_renders(self, client):
        resp = client.get("/chat")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

    def test_chat_page_has_input_area(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'id="messageInput"' in html
        assert 'id="btnSend"' in html

    def test_chat_page_has_sidebar(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'id="currentSession"' in html
        assert 'id="knowledgeList"' in html
        assert 'id="cacheStats"' in html

    def test_chat_page_has_search(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'id="searchInput"' in html
        assert 'id="searchResults"' in html
        assert 'id="searchAllSessions"' in html

    def test_chat_page_has_loading_overlay(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'id="loadingOverlay"' in html
        assert 'id="progressSteps"' in html

    def test_chat_page_has_web_toggle(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'id="btnToggleWeb"' in html
        assert 'id="webSearchLabel"' in html

    def test_chat_page_has_modals(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'id="sessionsModal"' in html
        assert 'id="historyModal"' in html

    def test_chat_page_has_font_awesome(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'font-awesome' in html or 'fontawesome' in html

    def test_chat_page_has_script(self, client):
        resp = client.get("/chat")
        html = resp.data.decode("utf-8")
        assert 'script.js' in html
        assert 'style.css' in html


class TestSessionSwitchDeleteAPI:
    """Test session switch and delete endpoints."""

    def _create_and_get_path(self, client, name):
        resp = client.post("/api/sessions", json={"name": name})
        data = resp.get_json()
        assert data["success"] is True
        return data["session_file"]

    def test_create_session_returns_valid_path(self, client):
        path = self._create_and_get_path(client, "path-test")
        assert "path-test" in path
        assert path.endswith(".json")

    def test_switch_session_by_listed_name(self, client):
        """Verify session switch works using path from the session list."""
        import web_ui
        path = self._create_and_get_path(client, "switch-me")
        # Call the session_manager directly to verify core logic works
        p = Path(path)
        label = web_ui.session_manager.session_label(p)
        assert label == "switch-me"

        # Test via flask session mechanism using session file path
        with client.session_transaction() as sess:
            sess["session_file"] = path

        # Now history should reflect this session
        resp = client.get("/api/history")
        assert resp.status_code == 200

    def test_delete_removes_from_list(self, client):
        path = self._create_and_get_path(client, "del-me")
        # Delete directly via session_manager (tested independently)
        import web_ui
        p = Path(path)
        assert p.exists()
        result = web_ui.session_manager.delete_session(p)
        assert result is True
        assert not p.exists()

    def test_list_sessions_includes_new(self, client):
        self._create_and_get_path(client, "list-api-test")
        resp = client.get("/api/sessions")
        names = [s["name"] for s in resp.get_json()["sessions"]]
        assert "list-api-test" in names


class TestChatPostAPI:
    """Test the POST /api/chat endpoint with valid input (mocked run_crew)."""

    @pytest.fixture(autouse=True)
    def _mock_run_crew(self, monkeypatch):
        """Mock run_crew to avoid actual LLM calls."""
        monkeypatch.setattr("web_ui.run_crew", lambda **kw: "Mocked answer.")

    def test_chat_with_valid_message(self, client):
        resp = client.post("/api/chat", json={
            "message": "什么是BERT？",
            "task_id": "test1234",
            "use_web_search": False,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "response" in data
        assert "timestamp" in data

    def test_chat_caches_answer(self, client):
        import web_ui
        web_ui.answer_cache.cache = []
        resp = client.post("/api/chat", json={
            "message": "cache test question",
            "use_web_search": False,
        })
        assert resp.status_code == 200
        assert resp.get_json()["from_cache"] is False
        # Second call should hit cache
        resp2 = client.post("/api/chat", json={
            "message": "cache test question",
            "use_web_search": False,
        })
        assert resp2.status_code == 200
        assert resp2.get_json()["from_cache"] is True

    def test_chat_with_web_search_on(self, client):
        resp = client.post("/api/chat", json={
            "message": "search test question",
            "use_web_search": True,
            "task_id": "search123",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestChatSSEAPI:
    """Test the SSE streaming endpoint."""

    def test_sse_requires_task_id(self, client):
        resp = client.get("/api/chat/stream")
        assert resp.status_code == 400

    def test_sse_streams_progress(self, client):
        import web_ui
        task_id = web_ui.status_tracker.create_task()

        resp = client.get(f"/api/chat/stream?task_id={task_id}")
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"

        web_ui.status_tracker.cleanup(task_id)


class TestKnowledgeAPI:
    """Test knowledge (file) management endpoints."""

    def test_list_knowledge_empty(self, client):
        resp = client.get("/api/knowledge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "files" in data

    def test_upload_rejects_no_file(self, client):
        resp = client.post("/api/knowledge/upload")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_upload_rejects_wrong_extension(self, client):
        data = {"file": (io.BytesIO(b"test"), "test.txt")}
        resp = client.post("/api/knowledge/upload", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 400
        d = resp.get_json()
        assert d["success"] is False

    def test_delete_nonexistent_file(self, client):
        resp = client.delete("/api/knowledge/nonexistent.pdf")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False

    def test_delete_with_path_traversal(self, client):
        # Flask normalizes `..` in URLs, so test with `/` separator
        resp = client.delete("/api/knowledge/..%2F..%2Fetc%2Fpasswd")
        # Either 400 (caught by check) or 404 (file not found after decode)
        assert resp.status_code in (400, 404)


class TestImageServingAPI:
    """Test the image serving endpoint."""

    def test_image_not_found(self, client):
        resp = client.get("/images/nonexistent.png")
        assert resp.status_code == 404

    def test_image_path_traversal_blocked(self, client):
        resp = client.get("/images/../../../etc/passwd")
        assert resp.status_code == 404


class TestStatusTrackerAPI:
    """Test the SSE status tracker lifecycle."""

    def test_create_task(self, client):
        import web_ui
        task_id = web_ui.status_tracker.create_task()
        assert len(task_id) == 8

    def test_update_task(self, client):
        import web_ui
        task_id = web_ui.status_tracker.create_task()
        web_ui.status_tracker.update(task_id, "routing", "正在分析...")
        # Should not raise
        web_ui.status_tracker.cleanup(task_id)

    def test_cleanup_nonexistent(self, client):
        import web_ui
        web_ui.status_tracker.cleanup("nonexist")  # should not raise
