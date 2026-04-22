"""Registration key generation for admin vault."""
import secrets

from app.extensions import db
from app.models import RegistrationKey


def generate_secure_code(prefix="FORGE", segments=2, segment_len=4):
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "-".join(
        "".join(secrets.choice(chars) for _ in range(segment_len))
        for _ in range(segments)
    )
    return f"{prefix}-{body}"


def create_bulk_keys(count, email=None, is_admin_test_key=False):
    new_keys = []
    for _ in range(count):
        code = (
            generate_secure_code(prefix="TEST", segments=2, segment_len=4)
            if is_admin_test_key
            else generate_secure_code()
        )
        key_obj = RegistrationKey(
            key_code=code,
            email=email,
            is_admin_test_key=is_admin_test_key,
        )
        db.session.add(key_obj)
        new_keys.append(code)
    return new_keys
