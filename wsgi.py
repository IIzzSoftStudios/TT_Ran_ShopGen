"""Production WSGI entrypoint for gunicorn / Cloud Run.

Gunicorn imports `application` from this module. Keeping the entrypoint thin
(no top-level work beyond importing the configured Flask app) means cold
starts on Cloud Run remain dominated by `create_app()` in `app/__init__.py`.
"""

from app import app as application

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=5000, debug=False)
