"""Tests for session management."""

import time
from freeact.session import Session, SessionManager


def test_session_creation():
    s = Session(name="test", browser_id="b1")
    assert s.name == "test"
    assert s.browser_id == "b1"
    assert s.age_seconds >= 0


def test_session_age():
    s = Session(name="test", browser_id="b1", created_at=time.time() - 3600)
    assert s.age_seconds >= 3599


def test_session_manager_create_get():
    sm = SessionManager()
    sm.create("s1", "b1")
    s = sm.get("s1")
    assert s is not None
    assert s.name == "s1"
    sm.close("s1")


def test_session_manager_list():
    sm = SessionManager()
    sm.create("s1", "b1")
    sessions = sm.list_sessions()
    names = [s.name for s in sessions]
    assert "s1" in names
    sm.close("s1")


def test_session_manager_duplicate_create():
    sm = SessionManager()
    sm.create("s1", "b1")
    sm.create("s1", "b2")
    s = sm.get("s1")
    assert s.browser_id == "b1"
    sm.close("s1")
