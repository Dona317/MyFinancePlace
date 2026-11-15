"""Production entry point: gunicorn -c gunicorn.conf.py wsgi:app (see docs/tecnica/DEPLOY.md)."""
from app import create_app

app = create_app("production")
