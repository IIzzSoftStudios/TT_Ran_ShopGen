import logging
import os

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import UserMixin, LoginManager
from flask_bcrypt import Bcrypt
from flask_session import Session
from flask_wtf import CSRFProtect
from flask_mailman import Mail

try:  # Flask-Limiter is an optional dep; if missing, all `limiter.limit`
      # decorators become no-ops so the app still boots.
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _LIMITER_AVAILABLE = True
except Exception:  # pragma: no cover
    Limiter = None  # type: ignore
    get_remote_address = None  # type: ignore
    _LIMITER_AVAILABLE = False


_extensions_logger = logging.getLogger(__name__)


db = SQLAlchemy()
migrate = Migrate()
user = UserMixin()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
session = Session()
csrf = CSRFProtect()
mail = Mail()


class _NoopLimiter:
    """Stand-in used when Flask-Limiter isn't installed.

    Exposes the `.limit(spec)` API as a decorator that returns the
    wrapped function untouched, so call sites don't branch.
    """

    def init_app(self, app):  # noqa: D401
        return None

    def limit(self, *_args, **_kwargs):
        def _decorator(fn):
            return fn
        return _decorator


def _resolve_limiter_storage_uri() -> str:
    """Pick a Redis URI for Flask-Limiter.

    Priority: explicit ``LIMITER_STORAGE_URI`` (lets ops put limiter on a
    different Redis DB or cluster than sessions/broker — see the
    redis-hot-path-split todo) → ``REDIS_URL`` → in-memory fallback.

    In production (``FLASK_ENV=production``), an in-memory backend is logged
    as a critical misconfiguration: per-process counters across multiple
    Cloud Run instances make every documented limit trivially bypassable
    (TDoS exposure on DB-heavy routes).

    ``TRSG_CLOUD_RUN_MIGRATE`` (Cloud Build one-shot job) intentionally uses
    in-memory limiter storage — no HTTP traffic and no cross-instance limits.
    """
    if os.getenv("TRSG_CLOUD_RUN_MIGRATE", "").lower() in ("1", "true", "yes"):
        return "memory://"
    explicit = os.getenv("LIMITER_STORAGE_URI")
    if explicit:
        return explicit
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    if os.getenv("FLASK_ENV", "development").lower() == "production":
        _extensions_logger.critical(
            "Flask-Limiter has no Redis storage configured (LIMITER_STORAGE_URI / "
            "REDIS_URL unset) in production; rate limits will be per-process and "
            "unenforceable across Cloud Run instances."
        )
    return "memory://"


if _LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri=_resolve_limiter_storage_uri(),
        # Failing closed on a transient Redis blip would lock every user out
        # of rate-limited endpoints; degrade gracefully and rely on Redis
        # health alerts instead.
        strategy="fixed-window",
        in_memory_fallback_enabled=True,
    )
else:  # pragma: no cover
    limiter = _NoopLimiter()