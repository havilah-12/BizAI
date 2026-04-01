"""Database-backed chat session helpers."""

from __future__ import annotations

SessionHistory = list[dict[str, str]]

from app.db import (
    append_turn as db_append_turn,
    clear_session as db_clear_session,
    create_session as db_create_session,
    delete_session as db_delete_session,
    get_history as db_get_history,
    list_sessions as db_list_sessions,
    update_session_name as db_update_session_name,
)


def create_session(user_email: str) -> str:
    return db_create_session(user_email)


def list_sessions(user_email: str) -> list[dict[str, str]]:
    return db_list_sessions(user_email)


def update_session_name(session_id: str, user_email: str, session_name: str) -> None:
    db_update_session_name(session_id, user_email, session_name)


def get_history(session_id: str, user_email: str) -> SessionHistory:
    return db_get_history(session_id, user_email)


def append_turn(session_id: str, user_email: str, role: str, content: str) -> None:
    if role not in {"user", "assistant"}:
        raise ValueError("Invalid role")
    db_append_turn(session_id, user_email, role, content)


def clear_session(session_id: str, user_email: str) -> None:
    db_clear_session(session_id, user_email)


def delete_session(session_id: str, user_email: str) -> None:
    db_delete_session(session_id, user_email)
