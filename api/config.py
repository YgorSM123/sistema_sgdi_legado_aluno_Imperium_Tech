import os

JWT_SECRET = os.environ.get("SGDI_JWT_SECRET") or os.environ.get("SECRET_KEY") or "sgdi-dev-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.environ.get("SGDI_JWT_EXPIRATION_HOURS", "24"))

API_CLIENT_ID = os.environ.get("SGDI_API_CLIENT_ID", "sgdi_integration")
API_CLIENT_SECRET = os.environ.get("SGDI_API_CLIENT_SECRET", "sgdi_api_secret_change_me")
