from flasgger import Swagger

from api.routes_audit import audit_bp
from api.routes_auth import auth_bp
from api.routes_comentarios import comentarios_bp
from api.routes_dashboard import dashboard_bp
from api.routes_demandas import demandas_bp
from api.routes_usuarios import usuarios_bp

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    # Login no Swagger grava o token automaticamente nas proximas chamadas
    "JWT_AUTH_URL_RULE": "/api/auth/login",
    "JWT_AUTH_HEADER_NAME": "Authorization",
    "JWT_AUTH_HEADER_TYPE": "Bearer",
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": (
                "Opcional se ja fez Login: cole Bearer + espaco + access_token "
                "(ex: Bearer eyJhbGciOi...)"
            ),
        }
    },
    "ui_params": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
    },
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "SGDI - API REST",
        "description": (
            "API REST do SGDI.\n\n"
            "**Como autenticar no Swagger:**\n"
            "1. Abra **Autenticacao > POST /api/auth/login**\n"
            "2. Clique em **Try it out**, use o body de exemplo e **Execute**\n"
            "3. O token e aplicado automaticamente nas demais APIs\n"
            "4. (Alternativa) Clique em **Authorize** (cadeado) e cole: `Bearer SEU_TOKEN`\n\n"
            "Credenciais padrao: client_id `sgdi_integration`, "
            "client_secret `sgdi_api_secret_change_me`"
        ),
        "version": "1.0.0",
        "contact": {
            "name": "Imperium Tech",
        },
    },
    "host": "localhost:5000",
    "basePath": "/",
    "schemes": ["http"],
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT obtido em POST /api/auth/login. Formato: Bearer <token>",
        }
    },
    "tags": [
        {"name": "Autenticacao", "description": "Obter token JWT"},
        {"name": "Demandas", "description": "CRUD de demandas via API"},
        {"name": "Usuarios", "description": "Gestao de usuarios via API"},
        {"name": "Comentarios", "description": "Comentarios das demandas via API"},
        {"name": "Dashboard", "description": "Indicadores e metricas via API"},
        {"name": "Auditoria", "description": "Historico de acoes e rastreabilidade"},
        {"name": "Web", "description": "Interface web HTML (legado)"},
    ],
}


def register_api(app):
    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)

    app.register_blueprint(auth_bp)
    app.register_blueprint(demandas_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(comentarios_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(audit_bp)
