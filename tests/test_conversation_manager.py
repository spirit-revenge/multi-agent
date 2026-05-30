import json
import tempfile
from pathlib import Path
from tools.conversation_manager import ConversationManager, ConversationMessage


class TestConversationMessage:
    """Test the ConversationMessage data class."""

    def test_create_message(self):
        msg = ConversationMessage("user", "Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_to_dict(self):
        msg = ConversationMessage("assistant", "Hi there")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there"
        assert "timestamp" in d

    def test_from_dict(self):
        data = {"role": "user", "content": "test", "timestamp": "2026-01-01T00:00:00"}
        msg = ConversationMessage.from_dict(data)
        assert msg.role == "user"
        assert msg.content == "test"


class TestConversationManager:
    """Test the conversation manager module."""

    def _make_mgr(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        return ConversationManager(session_file=tmp.name), Path(tmp.name)

    def test_empty_manager(self):
        mgr, path = self._make_mgr()
        assert len(mgr) == 0
        path.unlink(missing_ok=True)

    def test_add_message(self):
        mgr, path = self._make_mgr()
        mgr.add_message("user", "question 1")
        mgr.add_message("assistant", "answer 1")
        assert len(mgr) == 2
        assert mgr.history[0].role == "user"
        assert mgr.history[1].role == "assistant"
        path.unlink(missing_ok=True)

    def test_get_last_n_messages(self):
        mgr, path = self._make_mgr()
        for i in range(10):
            mgr.add_message("user", f"q{i}")
            mgr.add_message("assistant", f"a{i}")

        last4 = mgr.get_last_n_messages(4)
        assert len(last4) == 4
        # 20 messages total: indices 16-19 = q8, a8, q9, a9
        assert last4[0]["role"] == "user"
        assert last4[0]["content"] == "q8"
        path.unlink(missing_ok=True)

    def test_get_last_n_messages_returns_all_when_fewer(self):
        mgr, path = self._make_mgr()
        mgr.add_message("user", "only question")
        result = mgr.get_last_n_messages(10)
        assert len(result) == 1
        path.unlink(missing_ok=True)

    def test_clear_session(self):
        mgr, path = self._make_mgr()
        mgr.add_message("user", "test")
        mgr.clear_session()
        assert len(mgr) == 0
        assert not path.exists()
        path.unlink(missing_ok=True)

    def test_persistence(self):
        mgr1, path = self._make_mgr()
        mgr1.add_message("user", "hello")
        mgr1.add_message("assistant", "hi")

        mgr2 = ConversationManager(session_file=str(path))
        assert len(mgr2) == 2
        assert mgr2.history[0].content == "hello"
        path.unlink(missing_ok=True)

    def test_get_context_string_with_history(self):
        mgr, path = self._make_mgr()
        mgr.add_message("user", "What is AI?")
        mgr.add_message("assistant", "AI is artificial intelligence.")
        ctx = mgr.get_context_string(n=2)
        assert "What is AI?" in ctx
        assert "AI is artificial intelligence" in ctx
        path.unlink(missing_ok=True)

    def test_get_context_string_empty(self):
        mgr, path = self._make_mgr()
        ctx = mgr.get_context_string()
        assert "No previous conversation history" in ctx
        path.unlink(missing_ok=True)

    def test_get_full_context_for_agent(self):
        mgr, path = self._make_mgr()
        mgr.add_message("user", "Explain transformer")
        mgr.add_message("assistant", "A transformer is...")
        ctx = mgr.get_full_context_for_agent()
        assert "Explain transformer" in ctx
        assert "A transformer is" in ctx
        assert "之前的对话上下文" in ctx
        path.unlink(missing_ok=True)
