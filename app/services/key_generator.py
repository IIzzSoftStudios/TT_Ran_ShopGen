"""Registration key generation for admin vault."""
import secrets

from flask import current_app

from app.extensions import db
from app.models import RegistrationKey


def generate_secure_code(prefix="FORGE", segments=2, segment_len=4):
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "-".join(
        "".join(secrets.choice(chars) for _ in range(segment_len))
        for _ in range(segments)
    )
    return f"{prefix}-{body}"


def create_bulk_keys(count, email=None, is_admin_test_key=False, phase_slug=None):
    """Create keys; admin test keys always use phase ``test``."""
    pc = current_app.extensions["phase_config"]
    if is_admin_test_key:
        phase = "test"
        row = pc.get_phase("test")
        prefix = row["prefix"]
    else:
        if not phase_slug:
            phase_slug = "forge_master"
        if phase_slug not in pc.list_phases(include_internal=True):
            raise ValueError(f"Invalid phase slug: {phase_slug}")
        row = pc.get_phase(phase_slug)
        prefix = row["prefix"]
        phase = phase_slug

    new_keys = []
    for _ in range(count):
        code = generate_secure_code(prefix=prefix, segments=2, segment_len=4)
        key_obj = RegistrationKey(
            key_code=code,
            email=email,
            is_admin_test_key=is_admin_test_key,
            key_phase=phase,
        )
        db.session.add(key_obj)
        new_keys.append(code)
    return new_keys
