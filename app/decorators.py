<<<<<<< HEAD
"""Decorators for route protection. Admin routes return 404 to unauthorized users."""
from functools import wraps
=======
"""Route protection; admin routes return 404 to unauthorized users."""
from functools import wraps

>>>>>>> GCP
from flask import abort
from flask_login import current_user


def admin_required(f):
<<<<<<< HEAD
    """Require authenticated user with role GM. Return 404 (not 403) so route is invisible to scanners."""
=======
    """Require authenticated GM or vault_keeper."""

>>>>>>> GCP
    @wraps(f)
    def decorated_function(*args, **kwargs):
        is_authed = current_user.is_authenticated
        role = getattr(current_user, "role", None)
<<<<<<< HEAD

        allowed_roles = {"GM", "vault_keeper"}
        if not is_authed or role not in allowed_roles:
            abort(404)
        return f(*args, **kwargs)
=======
        allowed_roles = {"GM", "Both", "vault_keeper"}
        if not is_authed or role not in allowed_roles:
            abort(404)
        return f(*args, **kwargs)

>>>>>>> GCP
    return decorated_function
