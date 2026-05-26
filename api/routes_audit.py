import json

from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.auth import token_required
from api.paths import swagger_path
from api.serializers import rows_to_list

audit_bp = Blueprint("api_audit", __name__, url_prefix="/api/audit")


@audit_bp.route("/events", methods=["GET"])
@token_required
@swag_from(swagger_path("audit_events_list.yml"))
def listar_eventos():
    from app import get_db

    action = (request.args.get("action") or "").strip()
    entity_type = (request.args.get("entity_type") or "").strip()
    entity_id = request.args.get("entity_id")
    source = (request.args.get("source") or "").strip()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = max(int(request.args.get("offset", 0)), 0)

    sql = "SELECT * FROM audit_events WHERE 1=1"
    params = []

    if action:
        sql += " AND action = ?"
        params.append(action)
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id is not None and str(entity_id).strip():
        sql += " AND entity_id = ?"
        params.append(int(entity_id))
    if source:
        sql += " AND source = ?"
        params.append(source)

    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    total = conn.execute("SELECT COUNT(*) AS c FROM audit_events").fetchone()["c"]
    conn.close()

    eventos = rows_to_list(rows)
    for evento in eventos:
        if evento.get("details_json"):
            try:
                evento["details"] = json.loads(evento["details_json"])
            except (TypeError, ValueError):
                evento["details"] = evento["details_json"]
        evento.pop("details_json", None)

    return jsonify({"eventos": eventos, "total": total, "limit": limit, "offset": offset})
