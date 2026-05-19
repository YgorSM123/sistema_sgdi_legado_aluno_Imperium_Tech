from datetime import datetime

from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.auth import token_required
from api.paths import swagger_path
from api.serializers import row_to_dict, rows_to_list

comentarios_bp = Blueprint("api_comentarios", __name__, url_prefix="/api/comentarios")


@comentarios_bp.route("/demanda/<int:demanda_id>", methods=["GET"])
@token_required
@swag_from(swagger_path("comentarios_list.yml"))
def listar_comentarios(demanda_id):
    from app import get_db

    conn = get_db()
    demanda = conn.execute("SELECT id FROM demandas WHERE id = ?", (demanda_id,)).fetchone()
    if demanda is None:
        conn.close()
        return jsonify({"erro": "Demanda nao encontrada"}), 404

    rows = conn.execute(
        "SELECT * FROM comentarios WHERE demanda_id = ? ORDER BY id",
        (demanda_id,),
    ).fetchall()
    conn.close()
    return jsonify({"comentarios": rows_to_list(rows), "total": len(rows)})


@comentarios_bp.route("/demanda/<int:demanda_id>", methods=["POST"])
@token_required
@swag_from(swagger_path("comentarios_create.yml"))
def criar_comentario(demanda_id):
    from app import get_db

    data = request.get_json(silent=True) or {}
    comentario = (data.get("comentario") or "").strip()
    autor = (data.get("autor") or "").strip()
    if not comentario or not autor:
        return jsonify({"erro": "comentario e autor sao obrigatorios"}), 400

    conn = get_db()
    demanda = conn.execute("SELECT id FROM demandas WHERE id = ?", (demanda_id,)).fetchone()
    if demanda is None:
        conn.close()
        return jsonify({"erro": "Demanda nao encontrada"}), 404

    cursor = conn.execute(
        """
        INSERT INTO comentarios (demanda_id, comentario, autor, data)
        VALUES (?, ?, ?, ?)
        """,
        (demanda_id, comentario, autor, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({"id": new_id, "mensagem": "Comentario adicionado com sucesso"}), 201


@comentarios_bp.route("/<int:comentario_id>", methods=["DELETE"])
@token_required
@swag_from(swagger_path("comentarios_delete.yml"))
def excluir_comentario(comentario_id):
    from app import get_db

    conn = get_db()
    comentario = conn.execute(
        "SELECT id FROM comentarios WHERE id = ?",
        (comentario_id,),
    ).fetchone()
    if comentario is None:
        conn.close()
        return jsonify({"erro": "Comentario nao encontrado"}), 404

    conn.execute("DELETE FROM comentarios WHERE id = ?", (comentario_id,))
    conn.commit()
    conn.close()
    return jsonify({"mensagem": "Comentario excluido com sucesso"})
