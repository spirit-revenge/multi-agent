import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class ConversationMessage:
    """单条对话消息"""
    def __init__(self, role: str, content: str, timestamp: Optional[str] = None):
        self.role = role  # "user" 或 "assistant"
        self.content = content
        self.timestamp = timestamp or datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }
    
    @staticmethod
    def from_dict(data):
        return ConversationMessage(data["role"], data["content"], data.get("timestamp"))


class ConversationManager:
    """管理对话历史和持久化"""
    
    def __init__(self, session_file: str = "conversations/session.json"):
        self.session_file = Path(session_file)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.history: List[ConversationMessage] = []
        self.load_or_create_session()
    
    def load_or_create_session(self):
        """从文件加载或创建新会话"""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = [ConversationMessage.from_dict(msg) for msg in data.get("messages", [])]
                    logger.info("Loaded %d previous messages from session", len(self.history))
            except Exception as e:
                logger.warning("Failed to load session: %s. Starting fresh.", e)
                self.history = []
        else:
            self.history = []
    
    def save_session(self):
        """保存当前对话到文件"""
        with open(self.session_file, 'w', encoding='utf-8') as f:
            data = {"messages": [msg.to_dict() for msg in self.history]}
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_message(self, role: str, content: str):
        """添加一条消息"""
        msg = ConversationMessage(role, content)
        self.history.append(msg)
        self.save_session()
    
    def get_last_n_messages(self, n: int = 6) -> List[Dict]:
        """获取最近 n 条消息（用于 LLM 上下文）"""
        # 返回最近的 n 条消息，格式适合 prompt
        messages = self.history[-n:] if len(self.history) > n else self.history
        return [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in messages
        ]
    
    def get_context_string(self, n: int = 4) -> str:
        """获取格式化的对话历史字符串（用于 Agent prompt）"""
        messages = self.get_last_n_messages(n)
        if not messages:
            return "No previous conversation history."
        
        context = "--- 最近对话历史 ---\n"
        for msg in messages:
            role_name = "你" if msg["role"] == "user" else "助手"
            context += f"{role_name}: {msg['content'][:200]}...\n" if len(msg['content']) > 200 else f"{role_name}: {msg['content']}\n"
        return context + "--- 历史结束 ---\n"
    
    def get_full_context_for_agent(self) -> str:
        """获取完整的对话上下文供 Agent 参考"""
        if not self.history:
            return ""
        
        context = "## 之前的对话上下文\n\n"
        context += "用户之前询问过与讲座相关的问题，以下是对话历史：\n\n"
        
        for i, msg in enumerate(self.history[-4:]):
            if msg.role == "user":
                context += f"**用户问题 {i + 1}：** {msg.content[:300]}\n\n"
            else:
                summary = msg.content[:500] + ("..." if len(msg.content) > 500 else "")
                context += f"**之前的回答：** {summary}\n\n"
        
        return context
    
    def get_summary_context(self) -> str:
        """返回精简的对话历史摘要（≤300 token），替代完整历史。

        只保留最近一轮的问答摘要，避免长对话下 Token 膨胀。
        """
        if not self.history:
            return ""

        last_user = None
        last_assistant = None
        for msg in reversed(self.history):
            if msg.role == "user" and last_user is None:
                last_user = msg.content[:150]
            elif msg.role == "assistant" and last_assistant is None:
                last_assistant = msg.content[:200]

        parts = []
        if last_user:
            parts.append(f"用户上次问：{last_user}")
        if last_assistant:
            parts.append(f"上次回答：{last_assistant}")
        if not parts:
            return ""
        return "【历史摘要】" + " | ".join(parts)

    def clear_session(self):
        """清除对话历史"""
        self.history = []
        if self.session_file.exists():
            self.session_file.unlink()
        logger.info("Conversation history cleared")
    
    def __len__(self):
        return len(self.history)
    
    def __repr__(self):
        return f"ConversationManager(messages={len(self.history)})"
