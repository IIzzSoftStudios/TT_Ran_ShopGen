"""Map exceptions to user-visible strings without leaking hosts, ports, or SQL."""

from __future__ import annotations

from flask import current_app, has_app_context

from sqlalchemy.exc import SQLAlchemyError

# Shown when the real failure is a DB/driver issue (never echo driver text to clients).
_DB_PUBLIC = (
    "Could not save data right now. Please try again in a moment, or contact support "
    "if this continues."
)

_GENERIC_PUBLIC = "Something went wrong. Please try again."

_SIM_JOB_PUBLIC = (
    "Simulation failed due to a server error. Your world was not changed; you can try again."
)

# Defense-in-depth for errors written to Redis before sanitization shipped.
_JOB_ERROR_REDACT_MARKERS = (
    "psycopg2",
    "sqlalchemy",
    "operationalerror",
    "programmingerror",
    "statementerror",
    "dbapierror",
    "password authentication",
    "connection refused",
    "could not connect",
    "127.0.0.1",
    "/cloudsql/",
    "postgresql",
)


def redact_sim_job_error_for_client(msg: str | None) -> str | None:
    """Strip infrastructure details from legacy ``sim_job:*`` error strings."""
    if not msg or not isinstance(msg, str):
        return msg
    lowered = msg.lower()
    if any(n in lowered for n in _JOB_ERROR_REDACT_MARKERS):
        return _SIM_JOB_PUBLIC
    return msg


def public_error_message(exc: BaseException, *, audience: str = "http") -> str:
    """Return text safe for JSON/flash/HTML.

    ``audience``:
      - ``http`` — Flask JSON routes / flashes; full ``str(exc)`` only in debug mode
        for non-database errors.
      - ``redis_job`` — strings stored in ``sim_job:*`` and later read by the browser;
        never includes connection details (always safe for production).
    """
    if isinstance(exc, SQLAlchemyError):
        return _DB_PUBLIC
    if audience == "redis_job":
        return _SIM_JOB_PUBLIC
    if has_app_context() and current_app.debug:
        return str(exc)
    return _GENERIC_PUBLIC
