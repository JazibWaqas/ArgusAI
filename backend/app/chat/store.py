from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.report import ForensicReport


@dataclass
class SessionData:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    last_report: Optional[ForensicReport] = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionData] = {}

    def create(self) -> str:
        sid = str(uuid.uuid4())
        self._sessions[sid] = SessionData()
        return sid

    def get(self, session_id: str) -> Optional[SessionData]:
        return self._sessions.get(session_id)

    def append_message(self, session_id: str, role: str, content: str, extra: Optional[Dict[str, Any]] = None) -> bool:
        s = self.get(session_id)
        if not s:
            return False
        row: Dict[str, Any] = {"role": role, "content": content}
        if extra:
            row.update(extra)
        s.messages.append(row)
        return True

    def set_report(self, session_id: str, report: ForensicReport) -> bool:
        s = self.get(session_id)
        if not s:
            return False
        s.last_report = report
        return True


store = SessionStore()
