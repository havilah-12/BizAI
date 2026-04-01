"""Per-user document ingestion and retrieval for RAG."""

from __future__ import annotations

import io
import math
import os
import re
from pathlib import Path
from typing import Iterable

from langchain_openai import OpenAIEmbeddings
from pypdf import PdfReader

from app.db import (
    add_chunk,
    delete_knowledge as db_delete_knowledge,
    get_chunks,
    insert_document,
    knowledge_stats as db_knowledge_stats,
)

BASE = Path(__file__).resolve().parent.parent / "data"
UPLOADS = BASE / "uploads"


def _safe_user_key(email: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "_", email.lower())


def _chunk_text(text: str, size: int = 900, overlap: int = 120) -> Iterable[str]:
    cleaned = "\n".join([line.rstrip() for line in text.splitlines() if line.strip()])
    if not cleaned:
        return []
    out: list[str] = []
    i = 0
    while i < len(cleaned):
        out.append(cleaned[i : i + size])
        i += max(1, size - overlap)
    return out


def ingest_text(email: str, filename: str, text: str) -> int:
    chunks = list(_chunk_text(text))
    if not chunks:
        return 0
    document_id = insert_document(email, filename, "text/plain")
    embeddings = _embed_texts(chunks)
    for idx, chunk in enumerate(chunks):
        add_chunk(
            document_id=document_id,
            user_email=email,
            source=filename,
            chunk_id=str(idx),
            text_content=chunk,
            embedding=embeddings[idx] if idx < len(embeddings) else None,
        )
    return len(chunks)


def ingest_file(email: str, filename: str, content_type: str, data: bytes) -> int:
    filename = filename or "uploaded-file"
    content_type = (content_type or "").lower()

    user_dir = UPLOADS / _safe_user_key(email)
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / filename).write_bytes(data)

    text = ""
    if filename.lower().endswith(".pdf") or "pdf" in content_type:
        reader = PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
        text = "\n".join(pages)
    else:
        text = data.decode("utf-8", errors="ignore")

    return ingest_text(email, filename, text)


def _tokenize(s: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]{3,}", s.lower()))


def _embedding_model() -> OpenAIEmbeddings | None:
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    if not model:
        return None
    return OpenAIEmbeddings(model=model)


def _embed_texts(texts: list[str]) -> list[list[float]]:
    model = _embedding_model()
    if model is None or not texts:
        return []
    try:
        return [list(map(float, item)) for item in model.embed_documents(texts)]
    except Exception:
        return []


def _embed_query(query: str) -> list[float] | None:
    model = _embedding_model()
    if model is None or not query.strip():
        return None
    try:
        return list(map(float, model.embed_query(query)))
    except Exception:
        return None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return -1.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return numerator / (left_norm * right_norm)


def search_knowledge(email: str, query: str, k: int = 4) -> str:
    rows = get_chunks(email)
    if not rows:
        return "No company documents found. Ask user to upload policies/SOPs first."

    query_embedding = _embed_query(query)
    scored: list[tuple[float, dict[str, str]]] = []
    if query_embedding is not None:
        for row in rows:
            row_embedding = row.get("embedding")
            if isinstance(row_embedding, list):
                score = _cosine_similarity(query_embedding, row_embedding)
                if score > 0:
                    scored.append((score, row))

    if not scored:
        qtok = _tokenize(query)
        for row in rows:
            score = float(len(qtok.intersection(_tokenize(row["text"]))))
            if score > 0:
                scored.append((score, row))

    if not scored:
        return "No relevant internal policy found for this query."

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:k]
    blocks = []
    for i, (_, row) in enumerate(top, 1):
        blocks.append(
            f"[{i}] source={row['source']} chunk={row['chunk_id']}\n{row['text'][:700]}"
        )
    return "\n\n".join(blocks)


def delete_knowledge(email: str) -> None:
    db_delete_knowledge(email)


def knowledge_stats(email: str) -> dict[str, int]:
    return db_knowledge_stats(email)
