<<<<<<< HEAD
"""
Validators for auth and forms.
2026 Econo-Forge Security Standard: password complexity for registration and reset.
"""
import re


def is_password_strong(password):
    """
    Validates the 2026 Econo-Forge Security Standard:
    - 8+ Characters
    - 1+ Uppercase
    - 1+ Lowercase
    - 1+ Special Character (!@#$%^&*()_+)

    Returns:
        tuple: (bool success, str error_message). On success, error_message is "".
    """
=======
"""Password complexity for registration and reset."""
import re

# Minimum days before a previously used password may be chosen again (reset / change flows).
PASSWORD_REUSE_FORBIDDEN_DAYS = 180


def is_password_strong(password):
>>>>>>> GCP
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
<<<<<<< HEAD
    # Matches the frontend pattern: ! @ # $ % ^ & * ( ) _ +
=======
>>>>>>> GCP
    if not re.search(r"[!@#$%^&*()_+]", password):
        return False, "Password must contain at least one special character (!@#$%^&*()_+)."

    return True, ""
