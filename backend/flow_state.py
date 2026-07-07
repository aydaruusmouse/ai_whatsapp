"""Persist VAS / multi-step flow state per chat session."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from knowledge import _db, _lock

_DEFAULT = {
    "customer_phone": None,
    "flow_state": "idle",
    "flow_data": {},
}


def get_meta(session_id: str) -> dict[str, Any]:
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT customer_phone, flow_state, flow_data FROM session_meta WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
    if not row:
        return dict(_DEFAULT)
    data: dict[str, Any] = {}
    if row["flow_data"]:
        try:
            data = json.loads(row["flow_data"])
        except json.JSONDecodeError:
            data = {}
    return {
        "customer_phone": row["customer_phone"],
        "flow_state": row["flow_state"] or "idle",
        "flow_data": data,
    }


def set_meta(
    session_id: str,
    *,
    customer_phone: str | None = None,
    flow_state: str | None = None,
    flow_data: dict[str, Any] | None = None,
    reset_flow: bool = False,
) -> None:
    current = get_meta(session_id)
    phone = customer_phone if customer_phone is not None else current["customer_phone"]
    state = "idle" if reset_flow else (flow_state if flow_state is not None else current["flow_state"])
    data = {} if reset_flow else (flow_data if flow_data is not None else current["flow_data"])
    now = time.time()
    with _lock:
        with _db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT IGNORE INTO sessions (session_id, created_at) VALUES (%s, %s)",
                (session_id, now),
            )
            cur.execute(
                """
                INSERT INTO session_meta (session_id, customer_phone, flow_state, flow_data, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    customer_phone = VALUES(customer_phone),
                    flow_state = VALUES(flow_state),
                    flow_data = VALUES(flow_data),
                    updated_at = VALUES(updated_at)
                """,
                (session_id, phone, state, json.dumps(data), now),
            )


def reset_flow(session_id: str) -> None:
    meta = get_meta(session_id)
    set_meta(session_id, customer_phone=meta["customer_phone"], reset_flow=True)
