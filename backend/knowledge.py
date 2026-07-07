"""MariaDB/MySQL knowledge store with lexical retrieval for RAG-style context."""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import pymysql
from pymysql.cursors import DictCursor

# Load backend/.env before any DB_* reads (import order safe).
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

_MAMP_SOCKET = Path("/Applications/MAMP/tmp/mysql/mysql.sock")

_MAX_CHUNK = 1200
_MAX_TOTAL_CONTEXT_CHARS = 96_000

_QUERY_STOP_WORDS = frozenset({
    "maxay", "waa", "waxa", "wax", "ku", "ka", "ah", "ee", "oo", "iyo", "la", "ay",
    "what", "does", "is", "the", "a", "an", "how", "about", "tell", "me", "do",
    "qabataa", "qabato", "qabtaa", "sameeyo", "sameysaa", "sameeyaa", "bixisaa",
    "bixiyo", "who", "are", "you", "can", "ma", "mi", "ii", "iga",
})

_initialized = False
_lock = threading.Lock()

# All uploads/URLs share one knowledge pool (not per-browser session).
GLOBAL_KNOWLEDGE_SESSION = "telesom-global-knowledge"

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id VARCHAR(36) NOT NULL PRIMARY KEY,
        created_at DOUBLE NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        source VARCHAR(512) NOT NULL,
        text LONGTEXT NOT NULL,
        created_at DOUBLE NOT NULL,
        INDEX idx_chunks_session (session_id),
        CONSTRAINT fk_chunks_session
            FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS session_meta (
        session_id VARCHAR(36) NOT NULL PRIMARY KEY,
        customer_phone VARCHAR(64) NULL,
        flow_state VARCHAR(64) NOT NULL DEFAULT 'idle',
        flow_data TEXT NULL,
        updated_at DOUBLE NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


@dataclass
class _Chunk:
    text: str
    source: str  # filename or URL
    chunk_id: int = 0


def _db_settings() -> dict[str, Any]:
    settings: dict[str, Any] = {
        "user": os.getenv("DB_USER", "telesom"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "telesom_ai"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    socket_path = (os.getenv("DB_SOCKET") or "").strip()
    if not socket_path and _MAMP_SOCKET.is_socket():
        # MAMP on Mac: MySQL often listens on socket only, not TCP 8889.
        socket_path = str(_MAMP_SOCKET)
    if socket_path:
        settings["unix_socket"] = socket_path
    else:
        settings["host"] = os.getenv("DB_HOST", "127.0.0.1")
        settings["port"] = int(os.getenv("DB_PORT", "3306"))
    return settings


def db_label() -> str:
    s = _db_settings()
    db = s["database"]
    user = s["user"]
    if "unix_socket" in s:
        return f"mysql://{user}@socket:{s['unix_socket']}/{db}"
    return f"mysql://{user}@{s['host']}:{s['port']}/{db}"


def init_db() -> None:
    """Connect to MariaDB/MySQL and ensure tables exist. Call on app startup."""
    global _initialized
    try:
        with _lock:
            with _db() as conn:
                cur = conn.cursor()
                for stmt in _SCHEMA_STATEMENTS:
                    cur.execute(stmt)
                _ensure_session_row(cur, GLOBAL_KNOWLEDGE_SESSION)
                cur.execute(
                    "UPDATE chunks SET session_id = %s WHERE session_id != %s",
                    (GLOBAL_KNOWLEDGE_SESSION, GLOBAL_KNOWLEDGE_SESSION),
                )
            _initialized = True
    except pymysql.err.OperationalError as e:
        mode = db_label()
        raise RuntimeError(
            f"MariaDB/MySQL connection failed ({mode}): {e}. "
            "Hubi MAMP MySQL waa shidan yahay, DB_SOCKET, DB_USER, DB_PASSWORD, DB_NAME."
        ) from e


def db_status() -> dict[str, Any]:
    """For /health — connection info and total chunk count."""
    out: dict[str, Any] = {
        "knowledge_db": db_label(),
        "db_connected": False,
        "total_chunks_stored": 0,
    }
    if not _initialized:
        return out
    try:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM chunks")
            row = cur.fetchone()
            out["total_chunks_stored"] = int(row["n"]) if row else 0
            out["db_connected"] = True
    except Exception:
        pass
    return out


@contextmanager
def _db():
    conn = pymysql.connect(**_db_settings())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_session_row(cur: pymysql.cursors.Cursor, session_id: str) -> None:
    cur.execute(
        "INSERT IGNORE INTO sessions (session_id, created_at) VALUES (%s, %s)",
        (session_id, time.time()),
    )


def new_session() -> str:
    sid = str(uuid.uuid4())
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            _ensure_session_row(cur, sid)
    return sid


def ensure_session(session_id: str | None) -> str:
    if session_id:
        with _lock:
            with _db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT session_id FROM sessions WHERE session_id = %s",
                    (session_id,),
                )
                if cur.fetchone():
                    return session_id
    return new_session()


def clear_session(session_id: str) -> None:
    """Remove chunks for a session (user clicked Nadiifi xogta). Session row remains."""
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM chunks WHERE session_id = %s", (session_id,))


def add_text(session_id: str, text: str, source: str) -> int:
    text = _normalize(text)
    if not text:
        return 0
    pieces = _split_chunks(text)
    if not pieces:
        return 0
    now = time.time()
    source = source[:512]
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            _ensure_session_row(cur, session_id)
            cur.executemany(
                "INSERT INTO chunks (session_id, source, text, created_at) VALUES (%s, %s, %s, %s)",
                [(session_id, source, piece, now) for piece in pieces],
            )
    return len(pieces)


def _ensure_global_knowledge_session() -> None:
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            _ensure_session_row(cur, GLOBAL_KNOWLEDGE_SESSION)


def add_knowledge(text: str, source: str) -> int:
    """Add text to the shared Telesom knowledge base (all users/sessions)."""
    _ensure_global_knowledge_session()
    return add_text(GLOBAL_KNOWLEDGE_SESSION, text, source)


def total_chunk_count() -> int:
    """Total knowledge chunks across all uploads (shared pool)."""
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS n FROM chunks")
            row = cur.fetchone()
    return int(row["n"]) if row else 0


def clear_all_knowledge() -> None:
    """Remove all uploaded knowledge from DB (admin/maintenance only)."""
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM chunks")


def chunk_count(session_id: str) -> int:
    """Alias — knowledge is global; session_id is ignored."""
    return total_chunk_count()


def _load_all_chunks() -> list[_Chunk]:
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, source, text FROM chunks ORDER BY id",
            )
            rows = cur.fetchall()
    return [_Chunk(text=r["text"], source=r["source"], chunk_id=int(r["id"])) for r in rows]


def _expand_query_terms(terms: set[str]) -> set[str]:
    expanded = set(terms)
    corrections = {
        "antithefy": "antitheft",
        "antithef": "antitheft",
    }
    for t in list(terms):
        if t in corrections:
            expanded.add(corrections[t])
        if len(t) >= 5:
            expanded.add(t[:5])
    return expanded


def _term_matches(token: str, term: str) -> bool:
    if term == token:
        return True
    if len(term) >= 4 and len(token) >= 4 and term[:4] == token[:4]:
        return True
    return False


def _query_terms(query: str) -> set[str]:
    return _expand_query_terms(
        {t for t in _tokenize(query) if t not in _QUERY_STOP_WORDS and len(t) > 1}
    )


def _is_broad_telesom_query(query: str) -> bool:
    q = (query or "").lower()
    if "telesom" not in q:
        return False
    markers = (
        "maxay", "waxa", "what", "adeeg", "service", "qabata", "qabto", "qabta",
        "samee", "bixis", "about", "company", "shirkad",
    )
    return any(m in q for m in markers)


@dataclass
class RetrievalResult:
    text: str
    best_score: int
    chunks_included: int
    total_chunks: int


def retrieve_context(session_id: str, query: str, max_chunks: int | None = None) -> str:
    return retrieve_context_result(session_id, query, max_chunks=max_chunks).text


def retrieve_context_result(
    session_id: str,
    query: str,
    *,
    max_chunks: int | None = None,
) -> RetrievalResult:
    """Load knowledge-base chunks (as many as fit) ranked by query relevance."""
    chunks = _load_all_chunks()
    if not chunks:
        return RetrievalResult("", 0, 0, 0)

    q_terms = _query_terms(query)
    if not q_terms:
        q_terms = set()

    scored: list[tuple[int, _Chunk]] = []
    for ch in chunks:
        t = set(_tokenize(ch.text))
        score = 0
        for qt in q_terms:
            if qt in t:
                score += 2
                continue
            if any(_term_matches(tok, qt) for tok in t):
                score += 1
        if "telesom" in q_terms and "telesom" in t:
            score += 1
        scored.append((score, ch))

    scored.sort(key=lambda x: (-x[0], -x[1].chunk_id))
    best_score = scored[0][0] if scored else 0

    cap = max_chunks if max_chunks is not None else len(chunks)
    parts: list[str] = []
    total = 0
    included = 0
    for score, ch in scored:
        if score <= 0:
            continue
        if included >= cap:
            break
        block = f"[Ilaha: {ch.source}]\n{ch.text}"
        if total + len(block) > _MAX_TOTAL_CONTEXT_CHARS:
            if included == 0:
                parts.append(block[:_MAX_TOTAL_CONTEXT_CHARS])
                included = 1
            break
        parts.append(block)
        total += len(block)
        included += 1

    return RetrievalResult(
        text="\n\n---\n\n".join(parts),
        best_score=best_score,
        chunks_included=included,
        total_chunks=len(chunks),
    )


def _tokenize(s: str) -> list[str]:
    return re.findall(r"[\w']+", s.lower(), flags=re.UNICODE)


def _normalize(s: str) -> str:
    s = s.replace("\x00", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _split_chunks(text: str) -> list[str]:
    raw = re.split(r"\n\s*\n|\.(?=\s)", text)
    out: list[str] = []
    buf = ""
    for p in raw:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) + 1 > _MAX_CHUNK:
            if buf:
                out.append(buf)
            buf = p
        else:
            buf = f"{buf} {p}".strip() if buf else p
    if buf:
        out.append(buf)
    return out
