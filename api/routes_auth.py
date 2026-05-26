from flask import Blueprint, jsonify, make_response, request
from flasgger import swag_from

from api.audit import log_audit_event
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
        log_audit_event(
            "auth.login_failed",
            entity_type="auth",
            actor_type="api_client",
            actor_id=client_id or None,
            source="api",
            status_code=401,
            details={"client_id": client_id or None},
        )
        return jsonify({"erro": "Credenciais invalidas"}), 401

    token = create_access_token(client_id)
    if hasattr(token, "decode"):
        token = token.decode("utf-8")

    response = make_response(
        jsonify(
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 86400,
            }
        )
    )
    # Header usado pelo Swagger UI (Flasgger) para autenticar as demais requisicoes
    response.headers["jwt-token"] = token
    log_audit_event(
        "auth.login_success",
        entity_type="auth",
        actor_type="api_client",
        actor_id=client_id,
        source="api",
        status_code=200,
    )
    return response
