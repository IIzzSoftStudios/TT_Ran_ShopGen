"""Password complexity for registration and reset."""
import re


def is_password_strong(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"[!@#$%^&*()_+]", password):
        return False, "Password must contain at least one special character (!@#$%^&*()_+)."

    return True, ""
