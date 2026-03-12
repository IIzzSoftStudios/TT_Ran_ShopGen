"""
Shared registration key generation. Used by CLI script and Admin Bastion.
Confusion-free alphabet: no O, 0, I, 1.
"""
import secrets
from app.extensions import db
from app.models.users import RegistrationKey


def generate_secure_code(prefix="FORGE", segments=2, segment_len=4):
    """Generate a single key string. Confusion-free alphabet."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "-".join(
        "".join(secrets.choice(chars) for _ in range(segment_len))
        for _ in range(segments)
    )
    return f"{prefix}-{body}"


def create_bulk_keys(count):
    """
    Create `count` RegistrationKey rows. Caller must commit.
    Returns list of plaintext key codes (for audit/flash).
    """
    new_keys = []
    for _ in range(count):
        code = generate_secure_code()
        key_obj = RegistrationKey(key_code=code)
        db.session.add(key_obj)
        new_keys.append(code)
    return new_keys
