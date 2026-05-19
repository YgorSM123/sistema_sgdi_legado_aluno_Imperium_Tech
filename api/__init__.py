from flasgger import Swagger

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
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "SGDI - API REST",
        "description": (
            "API REST do Sistema de Gestao de Demandas Internas (SGDI). "
            "Permite consultar e manipular demandas, usuarios e comentarios. "
            "Rotas da interface web tambem estao documentadas na secao Web."
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
