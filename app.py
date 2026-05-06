"""Legacy module kept as a thin re-export.

Production uses `wsgi.py` (gunicorn entrypoint). The 404 handler that lived
here previously has moved into `create_app()` in `app/__init__.py` so it is
registered through the standard Flask factory path.
"""

from app import app

if __name__ == "__main__":
    app.run(debug=True)
