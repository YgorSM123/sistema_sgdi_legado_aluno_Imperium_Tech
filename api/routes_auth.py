from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.auth import create_access_token, validate_credentials
from api.paths import swagger_path

auth_bp = Blueprint("api_auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
@swag_from(swagger_path("auth_login.yml"))
def login():
    data = request.get_json(silent=True) or {}
    client_id = (data.get("client_id") or request.form.get("client_id") or "").strip()
    client_secret = (data.get("client_secret") or request.form.get("client_secret") or "").strip()

    if not validate_credentials(client_id, client_secret):
        return jsonify({"erro": "Credenciais invalidas"}), 401

    token = create_access_token(client_id)
    if hasattr(token, "decode"):
        token = token.decode("utf-8")

    return jsonify(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 86400,
        }
    )
