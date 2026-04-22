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


if _LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[],
    )
else:  # pragma: no cover
    limiter = _NoopLimiter()