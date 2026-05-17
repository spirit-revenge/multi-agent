"""
Utilities for managing multiple conversation sessions.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class SessionInfo:
    """Metadata for a single conversation session."""

    name: str
    file_path: Path
    message_count: int
    updated_at: str
    is_legacy: bool = False


class ConversationSessionManager:
    """Discover, create, and delete conversation session files."""

    def __init__(self, legacy_session_file: str = "conversations/session.json"):
        self.legacy_session_file = Path(legacy_session_file)
        self.sessions_dir = self.legacy_session_file.parent / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _read_session_metadata(self, file_path: Path) -> tuple[int, str]:
        message_count = 0

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                message_count = len(data.get("messages", []))
        except Exception:
            message_count = 0

        updated_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(timespec="seconds")
        return message_count, updated_at

    def _session_name_from_file(self, file_path: Path) -> str:
        if file_path == self.legacy_session_file:
            return "default"
        return file_path.stem

    def _slugify(self, value: str) -> str:
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = re.sub(r"-+", "-", value).strip("-")
        return value or "session"

    def list_sessions(self) -> List[SessionInfo]:
        sessions: List[SessionInfo] = []

        if self.legacy_session_file.exists():
            message_count, updated_at = self._read_session_metadata(self.legacy_session_file)
            sessions.append(
                SessionInfo(
                    name="default",
                    file_path=self.legacy_session_file,
                    message_count=message_count,
                    updated_at=updated_at,
                    is_legacy=True,
                )
            )

        for file_path in self.sessions_dir.glob("*.json"):
            message_count, updated_at = self._read_session_metadata(file_path)
            sessions.append(
                SessionInfo(
                    name=self._session_name_from_file(file_path),
                    file_path=file_path,
                    message_count=message_count,
                    updated_at=updated_at,
                    is_legacy=False,
                )
            )

        sessions.sort(
            key=lambda item: item.file_path.stat().st_mtime if item.file_path.exists() else 0,
            reverse=True,
        )
        return sessions

    def create_session(self, display_name: Optional[str] = None) -> Path:
        base_name = self._slugify(display_name or f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        candidate = self.sessions_dir / f"{base_name}.json"
        suffix = 1

        while candidate.exists() or candidate == self.legacy_session_file:
            candidate = self.sessions_dir / f"{base_name}-{suffix}.json"
            suffix += 1

        candidate.write_text(json.dumps({"messages": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return candidate

    def delete_session(self, file_path: Path) -> bool:
        if file_path == self.legacy_session_file:
            return False

        if not file_path.exists():
            return False

        file_path.unlink()
        return True

    def session_label(self, file_path: Path) -> str:
        if file_path == self.legacy_session_file:
            return "default"
        return file_path.stem
