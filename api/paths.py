import os

_API_DIR = os.path.dirname(os.path.abspath(__file__))


def swagger_path(filename):
    return os.path.join(_API_DIR, "swagger", filename)
