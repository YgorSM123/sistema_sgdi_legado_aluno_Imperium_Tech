from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import jsonify, request

from api.config import (
    API_CLIENT_ID,
    API_CLIENT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
)


def create_access_token(client_id=None):
    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "sub": client_id or API_CLIENT_ID,
        "exp": expires,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def validate_credentials(client_id, client_secret):
    return client_id == API_CLIENT_ID and client_secret == API_CLIENT_SECRET


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        if not token:
            return jsonify({"erro": "Token de autenticacao ausente. Use Authorization: Bearer <token>"}), 401
        try:
            decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"erro": "Token expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"erro": "Token invalido"}), 401
        return f(*args, **kwargs)

    return decorated
