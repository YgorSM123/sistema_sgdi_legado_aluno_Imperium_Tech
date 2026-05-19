from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.auth import token_required
from api.paths import swagger_path
from api.serializers import row_to_dict, rows_to_list

usuarios_bp = Blueprint("api_usuarios", __name__, url_prefix="/api/usuarios")


@usuarios_bp.route("", methods=["GET"])
@token_required
@swag_from(swagger_path("usuarios_list.yml"))
def listar_usuarios():
    from app import get_db

    conn = get_db()
    rows = conn.execute("SELECT id, nome FROM usuarios ORDER BY nome").fetchall()
    conn.close()
    return jsonify({"usuarios": rows_to_list(rows), "total": len(rows)})


@usuarios_bp.route("", methods=["POST"])
@token_required
@swag_from(swagger_path("usuarios_create.yml"))
def criar_usuario():
    from app import get_db

    data = request.get_json(silent=True) or {}
    nome = (data.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "nome e obrigatorio"}), 400

    conn = get_db()
    existente = conn.execute("SELECT id FROM usuarios WHERE nome = ?", (nome,)).fetchone()
    if existente:
        conn.close()
        return jsonify({"erro": "Usuario ja existe", "id": existente["id"]}), 409

    cursor = conn.execute("INSERT INTO usuarios (nome) VALUES (?)", (nome,))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({"id": new_id, "nome": nome, "mensagem": "Usuario criado com sucesso"}), 201


@usuarios_bp.route("/<int:usuario_id>", methods=["GET"])
@token_required
@swag_from(swagger_path("usuarios_get.yml"))
def obter_usuario(usuario_id):
    from app import get_db

    conn = get_db()
    usuario = conn.execute(
        "SELECT id, nome FROM usuarios WHERE id = ?",
        (usuario_id,),
    ).fetchone()
    conn.close()
    if usuario is None:
        return jsonify({"erro": "Usuario nao encontrado"}), 404
    return jsonify(row_to_dict(usuario))
