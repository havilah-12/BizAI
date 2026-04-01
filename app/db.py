"""Persistence helpers with SQLite fallback and PostgreSQL support."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except Exception:  # pragma: no cover - optional dependency at runtime
    create_engine = None
    text = None
    Engine = Any  # type: ignore[assignment]

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "bizai.db"
_ENGINE: Engine | None = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _use_sqlite() -> bool:
    return not _database_url()


def _sqlite_conn() -> sqlite3.Connection:
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_engine() -> Engine:
    global _ENGINE
    if create_engine is None or text is None:
        raise RuntimeError(
            "DATABASE_URL is set but SQLAlchemy is not installed. Run pip install -r requirements.txt."
        )
    if _ENGINE is None:
        _ENGINE = create_engine(_database_url(), future=True)
    return _ENGINE


@contextmanager
def db() -> Iterator[Any]:
    if _use_sqlite():
        conn = _sqlite_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    conn = get_engine().connect()
    tx = conn.begin()
    try:
        yield conn
        tx.commit()
    except Exception:
        tx.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    session_name TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    user_email TEXT NOT NULL,
                    source TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    embedding_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(knowledge_chunks)").fetchall()
            }
            if "embedding_json" not in columns:
                conn.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding_json TEXT")
            session_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()
            }
            if "session_name" not in session_columns:
                conn.execute("ALTER TABLE chat_sessions ADD COLUMN session_name TEXT")
        return

    with db() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    session_name TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id BIGSERIAL PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    document_id BIGINT NOT NULL,
                    user_email TEXT NOT NULL,
                    source TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    embedding_json TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_json TEXT")
        )
        conn.execute(
            text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS session_name TEXT")
        )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, hash_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(candidate.hex(), hash_hex)


def create_user(email: str, password_hash: str) -> None:
    if _use_sqlite():
        with db() as conn:
            existing = conn.execute(
                "SELECT email FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if existing:
                raise ValueError("Email already exists")
            conn.execute(
                "INSERT INTO users(email, password_hash) VALUES (?, ?)",
                (email, password_hash),
            )
        return
    with db() as conn:
        existing = conn.execute(
            text("SELECT email FROM users WHERE email = :email"),
            {"email": email},
        ).first()
        if existing:
            raise ValueError("Email already exists")
        conn.execute(
            text("INSERT INTO users(email, password_hash) VALUES (:email, :password_hash)"),
            {"email": email, "password_hash": password_hash},
        )


def ensure_user(email: str, password_hash: str) -> None:
    if get_user(email):
        return
    create_user(email, password_hash)


def get_user(email: str) -> dict[str, str] | None:
    if _use_sqlite():
        with db() as conn:
            row = conn.execute(
                "SELECT email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        return dict(row) if row else None
    with db() as conn:
        row = conn.execute(
            text("SELECT email, password_hash FROM users WHERE email = :email"),
            {"email": email},
        ).mappings().first()
    return dict(row) if row else None


def create_session(user_email: str) -> str:
    sid = str(uuid.uuid4())
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                "INSERT INTO chat_sessions(id, user_email) VALUES (?, ?)",
                (sid, user_email),
            )
        return sid
    with db() as conn:
        conn.execute(
            text("INSERT INTO chat_sessions(id, user_email) VALUES (:id, :user_email)"),
            {"id": sid, "user_email": user_email},
        )
    return sid


def require_session(session_id: str, user_email: str) -> None:
    if _use_sqlite():
        with db() as conn:
            row = conn.execute(
                "SELECT id FROM chat_sessions WHERE id = ? AND user_email = ?",
                (session_id, user_email),
            ).fetchone()
        if not row:
            raise ValueError("Unknown or unauthorized session")
        return
    with db() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM chat_sessions WHERE id = :id AND user_email = :user_email"
            ),
            {"id": session_id, "user_email": user_email},
        ).first()
    if not row:
        raise ValueError("Unknown or unauthorized session")


def list_sessions(user_email: str) -> list[dict[str, str]]:
    if _use_sqlite():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id,
                    COALESCE(
                        NULLIF(s.session_name, ''),
                        (
                            SELECT m.content
                            FROM messages m
                            WHERE m.session_id = s.id AND m.user_email = s.user_email AND m.role = 'user'
                            ORDER BY m.created_at ASC, m.id ASC
                            LIMIT 1
                        ),
                        s.id
                    ) AS session_title,
                    COALESCE(
                        (
                            SELECT m.content
                            FROM messages m
                            WHERE m.session_id = s.id AND m.user_email = s.user_email
                            ORDER BY m.created_at DESC, m.id DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS preview,
                    COALESCE(
                        (
                            SELECT m.created_at
                            FROM messages m
                            WHERE m.session_id = s.id AND m.user_email = s.user_email
                            ORDER BY m.created_at DESC, m.id DESC
                            LIMIT 1
                        ),
                        s.created_at
                    ) AS updated_at
                FROM chat_sessions s
                WHERE s.user_email = ?
                ORDER BY updated_at DESC
                """,
                (user_email,),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": str(row["session_title"])[:80],
                "preview": str(row["preview"])[:140],
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in rows
        ]
    with db() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    s.id,
                    COALESCE(
                        NULLIF(s.session_name, ''),
                        (
                            SELECT m.content
                            FROM messages m
                            WHERE m.session_id = s.id AND m.user_email = s.user_email AND m.role = 'user'
                            ORDER BY m.created_at ASC, m.id ASC
                            LIMIT 1
                        ),
                        s.id
                    ) AS session_title,
                    COALESCE(
                        (
                            SELECT m.content
                            FROM messages m
                            WHERE m.session_id = s.id AND m.user_email = s.user_email
                            ORDER BY m.created_at DESC, m.id DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS preview,
                    COALESCE(
                        (
                            SELECT m.created_at
                            FROM messages m
                            WHERE m.session_id = s.id AND m.user_email = s.user_email
                            ORDER BY m.created_at DESC, m.id DESC
                            LIMIT 1
                        ),
                        s.created_at
                    ) AS updated_at
                FROM chat_sessions s
                WHERE s.user_email = :user_email
                ORDER BY updated_at DESC
                """
            ),
            {"user_email": user_email},
        ).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "name": str(row["session_title"])[:80],
            "preview": str(row["preview"])[:140],
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in rows
    ]


def get_history(session_id: str, user_email: str) -> list[dict[str, str]]:
    require_session(session_id, user_email)
    if _use_sqlite():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = ? AND user_email = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id, user_email),
            ).fetchall()
        return [{"role": str(row["role"]), "content": str(row["content"])} for row in rows]
    with db() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = :session_id AND user_email = :user_email
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"session_id": session_id, "user_email": user_email},
        ).mappings().all()
    return [{"role": str(row["role"]), "content": str(row["content"])} for row in rows]


def append_turn(session_id: str, user_email: str, role: str, content: str) -> None:
    require_session(session_id, user_email)
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                """
                INSERT INTO messages(session_id, user_email, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, user_email, role, content),
            )
        return
    with db() as conn:
        conn.execute(
            text(
                """
                INSERT INTO messages(session_id, user_email, role, content)
                VALUES (:session_id, :user_email, :role, :content)
                """
            ),
            {
                "session_id": session_id,
                "user_email": user_email,
                "role": role,
                "content": content,
            },
        )


def clear_session(session_id: str, user_email: str) -> None:
    require_session(session_id, user_email)
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND user_email = ?",
                (session_id, user_email),
            )
        return
    with db() as conn:
        conn.execute(
            text(
                "DELETE FROM messages WHERE session_id = :session_id AND user_email = :user_email"
            ),
            {"session_id": session_id, "user_email": user_email},
        )


def delete_session(session_id: str, user_email: str) -> None:
    require_session(session_id, user_email)
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND user_email = ?",
                (session_id, user_email),
            )
            conn.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND user_email = ?",
                (session_id, user_email),
            )
        return
    with db() as conn:
        conn.execute(
            text(
                "DELETE FROM messages WHERE session_id = :session_id AND user_email = :user_email"
            ),
            {"session_id": session_id, "user_email": user_email},
        )
        conn.execute(
            text(
                "DELETE FROM chat_sessions WHERE id = :session_id AND user_email = :user_email"
            ),
            {"session_id": session_id, "user_email": user_email},
        )


def insert_document(user_email: str, filename: str, content_type: str) -> int:
    if _use_sqlite():
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO documents(user_email, filename, content_type)
                VALUES (?, ?, ?)
                """,
                (user_email, filename, content_type),
            )
            return int(cur.lastrowid)
    with db() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO documents(user_email, filename, content_type)
                VALUES (:user_email, :filename, :content_type)
                """
            ),
            {
                "user_email": user_email,
                "filename": filename,
                "content_type": content_type,
            },
        )
        inserted_id = result.lastrowid
        if inserted_id is not None:
            return int(inserted_id)
        row = conn.execute(text("SELECT MAX(id) FROM documents")).first()
        return int(row[0])


def add_chunk(
    document_id: int,
    user_email: str,
    source: str,
    chunk_id: str,
    text_content: str,
    embedding: list[float] | None = None,
) -> None:
    embedding_json = json.dumps(embedding) if embedding is not None else None
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_chunks(document_id, user_email, source, chunk_id, text_content, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (document_id, user_email, source, chunk_id, text_content, embedding_json),
            )
        return
    with db() as conn:
        conn.execute(
            text(
                """
                INSERT INTO knowledge_chunks(document_id, user_email, source, chunk_id, text_content, embedding_json)
                VALUES (:document_id, :user_email, :source, :chunk_id, :text_content, :embedding_json)
                """
            ),
            {
                "document_id": document_id,
                "user_email": user_email,
                "source": source,
                "chunk_id": chunk_id,
                "text_content": text_content,
                "embedding_json": embedding_json,
            },
        )


def get_chunks(user_email: str) -> list[dict[str, str]]:
    if _use_sqlite():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT source, chunk_id, text_content, embedding_json
                FROM knowledge_chunks
                WHERE user_email = ?
                ORDER BY id ASC
                """,
                (user_email,),
            ).fetchall()
        return [
            {
                "source": str(row["source"]),
                "chunk_id": str(row["chunk_id"]),
                "text": str(row["text_content"]),
                "embedding": json.loads(row["embedding_json"]) if row["embedding_json"] else None,
            }
            for row in rows
        ]
    with db() as conn:
        rows = conn.execute(
            text(
                """
                SELECT source, chunk_id, text_content, embedding_json
                FROM knowledge_chunks
                WHERE user_email = :user_email
                ORDER BY id ASC
                """
            ),
            {"user_email": user_email},
        ).mappings().all()
    return [
        {
            "source": str(row["source"]),
            "chunk_id": str(row["chunk_id"]),
            "text": str(row["text_content"]),
            "embedding": json.loads(row["embedding_json"]) if row["embedding_json"] else None,
        }
        for row in rows
    ]


def delete_knowledge(user_email: str) -> None:
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                "DELETE FROM knowledge_chunks WHERE user_email = ?",
                (user_email,),
            )
            conn.execute(
                "DELETE FROM documents WHERE user_email = ?",
                (user_email,),
            )
        return
    with db() as conn:
        conn.execute(
            text("DELETE FROM knowledge_chunks WHERE user_email = :user_email"),
            {"user_email": user_email},
        )
        conn.execute(
            text("DELETE FROM documents WHERE user_email = :user_email"),
            {"user_email": user_email},
        )


def knowledge_stats(user_email: str) -> dict[str, int]:
    if _use_sqlite():
        with db() as conn:
            chunks = conn.execute(
                "SELECT COUNT(*) FROM knowledge_chunks WHERE user_email = ?",
                (user_email,),
            ).fetchone()
            documents = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE user_email = ?",
                (user_email,),
            ).fetchone()
        return {"chunks": int(chunks[0] or 0), "documents": int(documents[0] or 0)}
    with db() as conn:
        chunks = conn.execute(
            text("SELECT COUNT(*) FROM knowledge_chunks WHERE user_email = :user_email"),
            {"user_email": user_email},
        ).first()
        documents = conn.execute(
            text("SELECT COUNT(*) FROM documents WHERE user_email = :user_email"),
            {"user_email": user_email},
        ).first()
    return {"chunks": int(chunks[0] or 0), "documents": int(documents[0] or 0)}


def update_session_name(session_id: str, user_email: str, session_name: str) -> None:
    if _use_sqlite():
        with db() as conn:
            conn.execute(
                "UPDATE chat_sessions SET session_name = ? WHERE id = ? AND user_email = ?",
                (session_name, session_id, user_email),
            )
        return
    with db() as conn:
        conn.execute(
            text(
                "UPDATE chat_sessions SET session_name = :session_name WHERE id = :id AND user_email = :user_email"
            ),
            {"session_name": session_name, "id": session_id, "user_email": user_email},
        )
