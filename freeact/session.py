"""Session management for FreeAct."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from freeact.config import SESSIONS_DIR


@dataclass
class Session:
    name: str
    browser_id: str
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._load_sessions()

    def _session_file(self, name: str) -> Path:
        return SESSIONS_DIR / f"{name}.json"

    def _load_sessions(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                session = Session(
                    name=data["name"],
                    browser_id=data["browser_id"],
                    created_at=data.get("created_at", time.time()),
                    last_used=data.get("last_used", time.time()),
                )
                if session.age_seconds < 28800:
                    self._sessions[session.name] = session
            except (json.JSONDecodeError, KeyError):
                pass
        self._cleanup_expired()

    def _save_session(self, session: Session):
        existing = {}
        f = self._session_file(session.name)
        if f.exists():
            try:
                existing = json.loads(f.read_text())
            except (json.JSONDecodeError):
                pass
        data = {
            "name": session.name,
            "browser_id": session.browser_id,
            "created_at": session.created_at,
            "last_used": session.last_used,
        }
        if "url" in existing:
            data["url"] = existing["url"]
        f.write_text(json.dumps(data))

    def _cleanup_expired(self):
        expired = [
            name
            for name, s in self._sessions.items()
            if s.age_seconds >= 28800
        ]
        for name in expired:
            self.close(name, cleanup_files=True)

    def create(self, name: str, browser_id: str) -> Session:
        if name in self._sessions:
            session = self._sessions[name]
            session.last_used = time.time()
            self._save_session(session)
            return session
        session = Session(name=name, browser_id=browser_id)
        self._sessions[name] = session
        self._save_session(session)
        return session

    def get(self, name: str) -> Session | None:
        session = self._sessions.get(name)
        if session:
            if session.age_seconds >= 28800:
                self.close(name, cleanup_files=True)
                return None
            session.last_used = time.time()
            self._save_session(session)
        return session

    def list_sessions(self) -> list[Session]:
        self._cleanup_expired()
        return list(self._sessions.values())

    def close(self, name: str, cleanup_files: bool = True):
        if name in self._sessions:
            del self._sessions[name]
        if cleanup_files:
            f = self._session_file(name)
            if f.exists():
                f.unlink()

    def close_all(self):
        for name in list(self._sessions.keys()):
            self.close(name)


_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
