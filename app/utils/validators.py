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
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    # Matches the frontend pattern: ! @ # $ % ^ & * ( ) _ +
    if not re.search(r"[!@#$%^&*()_+]", password):
        return False, "Password must contain at least one special character (!@#$%^&*()_+)."

    return True, ""
