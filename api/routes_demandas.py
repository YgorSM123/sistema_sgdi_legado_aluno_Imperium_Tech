from datetime import datetime

from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.audit import log_audit_event
from api.auth import token_required
from api.paths import swagger_path
from api.serializers import row_to_dict, rows_to_list

demandas_bp = Blueprint("api_demandas", __name__, url_prefix="/api/demandas")


def _get_helpers():
    from app import (
        PRIORIDADES_VALIDAS,
        STATUS_VALIDOS,
        _normalizar_prioridade,
        _parse_solicitante_id,
        get_db,
    )

    return get_db, _normalizar_prioridade, _parse_solicitante_id, PRIORIDADES_VALIDAS, STATUS_VALIDOS


@demandas_bp.route("", methods=["GET"])
@token_required
@swag_from(swagger_path("demandas_list.yml"))
def listar_demandas():
    get_db, _normalizar_prioridade, _, _, _ = _get_helpers()
    status = (request.args.get("status") or "").strip()
    prioridade = _normalizar_prioridade(request.args.get("prioridade"), default="")
    q = (request.args.get("q") or "").strip()
    solicitante_id = request.args.get("solicitante_id")

    sql = """
        SELECT
            d.id, d.titulo, d.descricao, d.data_criacao, d.prioridade,
            d.status, d.data_finalizacao, d.solicitante_id, u.nome AS solicitante
        FROM demandas d
        JOIN usuarios u ON u.id = d.solicitante_id
        WHERE 1=1
    """
    params = []

    if status in ("Aberta", "Finalizada"):
        sql += " AND d.status = ?"
        params.append(status)
    if prioridade:
        sql += " AND d.prioridade = ?"
        params.append(prioridade)
    if solicitante_id:
        sql += " AND d.solicitante_id = ?"
        params.append(int(solicitante_id))
    if q:
        sql += " AND (d.titulo LIKE ? OR d.descricao LIKE ? OR u.nome LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])

    sql += " ORDER BY d.id DESC"

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify({"demandas": rows_to_list(rows), "total": len(rows)})


@demandas_bp.route("/<int:demanda_id>", methods=["GET"])
@token_required
@swag_from(swagger_path("demandas_get.yml"))
def obter_demanda(demanda_id):
    get_db, _, _, _, _ = _get_helpers()
    conn = get_db()
    demanda = conn.execute(
        """
        SELECT
            d.id, d.titulo, d.descricao, d.data_criacao, d.prioridade,
            d.status, d.data_finalizacao, d.solicitante_id, u.nome AS solicitante
        FROM demandas d
        JOIN usuarios u ON u.id = d.solicitante_id
        WHERE d.id = ?
        """,
        (demanda_id,),
    ).fetchone()
    if demanda is None:
        conn.close()
        return jsonify({"erro": "Demanda nao encontrada"}), 404

    comentarios = conn.execute(
        "SELECT * FROM comentarios WHERE demanda_id = ? ORDER BY id",
        (demanda_id,),
    ).fetchall()
    conn.close()

    payload = row_to_dict(demanda)
    payload["comentarios"] = rows_to_list(comentarios)
    return jsonify(payload)


@demandas_bp.route("", methods=["POST"])
@token_required
@swag_from(swagger_path("demandas_create.yml"))
def criar_demanda():
    get_db, _normalizar_prioridade, _parse_solicitante_id, _, STATUS_VALIDOS = _get_helpers()
    data = request.get_json(silent=True) or {}
    titulo = (data.get("titulo") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    solicitante_id = _parse_solicitante_id(data.get("solicitante_id"))
    prioridade = _normalizar_prioridade(data.get("prioridade"))
    status = (data.get("status") or "Aberta").strip()

    if not titulo or not descricao:
        return jsonify({"erro": "titulo e descricao sao obrigatorios"}), 400
    if solicitante_id is None:
        return jsonify({"erro": "solicitante_id invalido"}), 400
    if status not in STATUS_VALIDOS:
        return jsonify({"erro": f"status deve ser um de: {', '.join(STATUS_VALIDOS)}"}), 400

    conn = get_db()
    usuario = conn.execute("SELECT id FROM usuarios WHERE id = ?", (solicitante_id,)).fetchone()
    if usuario is None:
        conn.close()
        return jsonify({"erro": "Solicitante nao encontrado"}), 404

    data_criacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        """
        INSERT INTO demandas (titulo, descricao, solicitante_id, data_criacao, prioridade, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (titulo, descricao, solicitante_id, data_criacao, prioridade, status),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    log_audit_event(
        "demanda.create",
        entity_type="demanda",
        entity_id=new_id,
        business_actor=solicitante_id,
        source="api",
        status_code=201,
        details={"titulo": titulo, "prioridade": prioridade, "status": status},
    )
    return jsonify({"id": new_id, "mensagem": "Demanda criada com sucesso"}), 201


@demandas_bp.route("/<int:demanda_id>", methods=["PUT"])
@token_required
@swag_from(swagger_path("demandas_update.yml"))
def atualizar_demanda(demanda_id):
    get_db, _normalizar_prioridade, _parse_solicitante_id, _, _ = _get_helpers()
    data = request.get_json(silent=True) or {}

    conn = get_db()
    demanda = conn.execute("SELECT * FROM demandas WHERE id = ?", (demanda_id,)).fetchone()
    if demanda is None:
        conn.close()
        return jsonify({"erro": "Demanda nao encontrada"}), 404

    titulo = (data.get("titulo") or demanda["titulo"]).strip()
    descricao = (data.get("descricao") or demanda["descricao"]).strip()
    solicitante_id = _parse_solicitante_id(data.get("solicitante_id", demanda["solicitante_id"]))
    prioridade = _normalizar_prioridade(
        data.get("prioridade"),
        default=demanda["prioridade"] or "media",
    )

    if solicitante_id is None:
        conn.close()
        return jsonify({"erro": "solicitante_id invalido"}), 400

    usuario = conn.execute("SELECT id FROM usuarios WHERE id = ?", (solicitante_id,)).fetchone()
    if usuario is None:
        conn.close()
        return jsonify({"erro": "Solicitante nao encontrado"}), 404

    old_values = row_to_dict(demanda)
    conn.execute(
        """
        UPDATE demandas
        SET titulo = ?, descricao = ?, solicitante_id = ?, prioridade = ?
        WHERE id = ?
        """,
        (titulo, descricao, solicitante_id, prioridade, demanda_id),
    )
    conn.commit()
    conn.close()
    log_audit_event(
        "demanda.update",
        entity_type="demanda",
        entity_id=demanda_id,
        business_actor=solicitante_id,
        source="api",
        details={
            "antes": old_values,
            "depois": {
                "titulo": titulo,
                "descricao": descricao,
                "solicitante_id": solicitante_id,
                "prioridade": prioridade,
            },
        },
    )
    return jsonify({"mensagem": "Demanda atualizada com sucesso"})


@demandas_bp.route("/<int:demanda_id>", methods=["DELETE"])
@token_required
@swag_from(swagger_path("demandas_delete.yml"))
def excluir_demanda(demanda_id):
    get_db, _, _, _, _ = _get_helpers()
    conn = get_db()
    demanda = conn.execute("SELECT * FROM demandas WHERE id = ?", (demanda_id,)).fetchone()
    if demanda is None:
        conn.close()
        return jsonify({"erro": "Demanda nao encontrada"}), 404

    snapshot = row_to_dict(demanda)
    conn.execute("DELETE FROM demandas WHERE id = ?", (demanda_id,))
    conn.commit()
    conn.close()
    log_audit_event(
        "demanda.delete",
        entity_type="demanda",
        entity_id=demanda_id,
        business_actor=snapshot.get("solicitante_id"),
        source="api",
        details={"excluido": snapshot},
    )
    return jsonify({"mensagem": "Demanda excluida com sucesso"})


@demandas_bp.route("/<int:demanda_id>/finalizar", methods=["POST"])
@token_required
@swag_from(swagger_path("demandas_finalizar.yml"))
def finalizar_demanda(demanda_id):
    get_db, _, _, _, _ = _get_helpers()
    conn = get_db()
    demanda = conn.execute("SELECT * FROM demandas WHERE id = ?", (demanda_id,)).fetchone()
    if demanda is None:
        conn.close()
        return jsonify({"erro": "Demanda nao encontrada"}), 404

    data_finalizacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE demandas
        SET status = 'Finalizada', data_finalizacao = ?
        WHERE id = ?
        """,
        (data_finalizacao, demanda_id),
    )
    conn.commit()
    conn.close()
    log_audit_event(
        "demanda.finalize",
        entity_type="demanda",
        entity_id=demanda_id,
        business_actor=demanda["solicitante_id"],
        source="api",
        details={"data_finalizacao": data_finalizacao},
    )
    return jsonify({"mensagem": "Demanda finalizada com sucesso"})
