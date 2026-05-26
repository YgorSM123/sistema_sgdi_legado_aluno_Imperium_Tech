import json
from datetime import datetime

from flask import g, has_request_context, request

AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    business_actor TEXT,
    source TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    request_method TEXT,
    request_path TEXT,
    status_code INTEGER,
    details_json TEXT
)
"""

AUDIT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_audit_occurred_at ON audit_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);
"""


def ensure_audit_table(conn):
    conn.executescript(AUDIT_TABLE_SQL + ";" + AUDIT_INDEX_SQL)


def _request_context(request_obj=None):
    if not has_request_context() and request_obj is None:
        return {}
    req = request_obj or request
    return {
        "ip_address": req.remote_addr,
        "user_agent": (req.headers.get("User-Agent") or "")[:512],
        "request_method": req.method,
        "request_path": req.path,
    }


def _resolve_actor(actor_type=None, actor_id=None, source="api"):
    if actor_id is not None:
        resolved_type = actor_type or ("api_client" if source == "api" else "web_unauthenticated")
        return resolved_type, str(actor_id)

    if has_request_context() and getattr(g, "client_id", None):
        return "api_client", str(g.client_id)

    if source == "web":
        return "web_unauthenticated", None

    return actor_type or "api_client", actor_id


def log_audit_event(
    action,
    *,
    entity_type=None,
    entity_id=None,
    actor_type=None,
    actor_id=None,
    business_actor=None,
    source="api",
    status_code=200,
    details=None,
    request_obj=None,
):
    """Registra um evento de auditoria no banco. Falhas nao interrompem a operacao principal."""
    try:
        from app import get_db

        resolved_type, resolved_id = _resolve_actor(actor_type, actor_id, source)
        ctx = _request_context(request_obj)
        business_actor_str = None
        if business_actor is not None:
            business_actor_str = str(business_actor)

        details_json = None
        if details is not None:
            details_json = json.dumps(details, ensure_ascii=False, default=str)

        conn = get_db()
        conn.execute(
            """
            INSERT INTO audit_events (
                occurred_at, action, entity_type, entity_id,
                actor_type, actor_id, business_actor, source,
                ip_address, user_agent, request_method, request_path,
                status_code, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                action,
                entity_type,
                entity_id,
                resolved_type,
                resolved_id,
                business_actor_str,
                source,
                ctx.get("ip_address"),
                ctx.get("user_agent"),
                ctx.get("request_method"),
                ctx.get("request_path"),
                status_code,
                details_json,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
