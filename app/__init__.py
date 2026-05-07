import json
import logging
import os
import sys

import redis
from dotenv import load_dotenv
from flask import Flask, request, render_template
from flask.sessions import SecureCookieSession, SecureCookieSessionInterface

from app.extensions import db, migrate, bcrypt, login_manager, session, csrf, mail, limiter
from app.models import User
from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path
from app.services.schema_compat import (
    drop_campaign_player_table,
    ensure_campaign_debt_column,
    ensure_campaign_current_game_day_column,
    ensure_campaign_scope_columns,
    ensure_deleted_campaign_sim_snapshot_table,
    ensure_gm_world_state_campaign_id,
    ensure_join_codes_columns,
    ensure_phase_entitlement_columns,
    ensure_player_campaign_id,
    ensure_player_npc_columns,
    ensure_region_campaign_only,
    ensure_sim_rules_table,
    ensure_simulation_logs_table,
    ensure_simulation_state_campaign_id,
    ensure_simulation_state_click_columns,
    ensure_solo_player_vault_schema,
    ensure_user_password_history_table,
    ensure_world_tables_campaign_only,
    preflight_campaign_rekey,
    warn_if_campaign_current_game_day_applied,
    warn_if_campaign_debt_column_applied,
    warn_if_campaign_player_dropped,
    warn_if_compat_mode_applied,
    warn_if_deleted_campaign_sim_snapshot_table_created,
    warn_if_gm_world_state_campaign_applied,
    warn_if_join_codes_compat_applied,
    warn_if_password_history_compat_applied,
    warn_if_phase_compat_applied,
    warn_if_player_campaign_applied,
    warn_if_player_npc_compat_applied,
    warn_if_preflight_applied,
    warn_if_region_campaign_only_applied,
    warn_if_sim_rules_table_created,
    warn_if_simulation_logs_table_created,
    warn_if_simulation_state_campaign_applied,
    warn_if_simulation_state_clicks_applied,
    warn_if_solo_vault_compat_applied,
    warn_if_world_tables_campaign_only_applied,
)

load_dotenv("config.env")

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Emit JSON to stdout so Cloud Logging parses severity and custom fields.

    Falls back to a stdlib JSON formatter if `python-json-logger` is missing
    so the app still boots in environments where that wheel isn't installed.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    try:
        from pythonjsonlogger import jsonlogger

        handler.setFormatter(
            jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"levelname": "severity"},
            )
        )
    except ImportError:

        class _JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload = {
                    "severity": record.levelname,
                    "name": record.name,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(payload)

        handler.setFormatter(_JsonFormatter())

    root.addHandler(handler)
    root.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))


def _resolve_required_config() -> tuple[str, str | None]:
    """Hard fail-fast in production if SECRET_KEY or DB URI are missing.

    Cloud Run will mark the revision unhealthy on `sys.exit(1)` and refuse to
    roll forward, which is the desired behavior vs. silently serving with a
    placeholder secret.
    """
    flask_env = os.getenv("FLASK_ENV", "development").lower()
    secret_key = os.getenv("SECRET_KEY")
    db_uri = os.getenv("SQLALCHEMY_DATABASE_URI")

    if flask_env == "production":
        missing = [
            name
            for name, value in (("SECRET_KEY", secret_key), ("SQLALCHEMY_DATABASE_URI", db_uri))
            if not value
        ]
        if missing:
            sys.stderr.write(f"CRITICAL: missing required env in production: {missing}\n")
            sys.exit(1)
    else:
        secret_key = secret_key or "dev_only_insecure_key"

    return secret_key, db_uri


class _ResilientSessionInterface:
    """Development fallback when Redis cannot load an existing session cookie."""

    def __init__(self, primary):
        self.primary = primary
        self.fallback = SecureCookieSessionInterface()

    def __getattr__(self, name):
        return getattr(self.primary, name)

    def open_session(self, app, request):
        try:
            loaded = self.primary.open_session(app, request)
        except Exception as exc:
            app.logger.warning(
                "Redis session open failed; falling back to signed cookie session: %s",
                exc,
            )
            return self.fallback.open_session(app, request)
        if loaded is None:
            app.logger.warning(
                "Redis session open returned None; falling back to signed cookie session."
            )
            return self.fallback.open_session(app, request)
        return loaded

    def save_session(self, app, session_obj, response):
        if isinstance(session_obj, SecureCookieSession):
            return self.fallback.save_session(app, session_obj, response)
        try:
            return self.primary.save_session(app, session_obj, response)
        except Exception as exc:
            app.logger.warning(
                "Redis session save failed; writing signed cookie session instead: %s",
                exc,
            )
            return self.fallback.save_session(app, session_obj, response)


def _install_dev_session_fallback(app: Flask) -> None:
    flask_env = os.getenv("FLASK_ENV", "development").lower()
    enabled = os.getenv(
        "SESSION_REDIS_FALLBACK", "false" if flask_env == "production" else "true"
    ).lower() in ("1", "true", "yes")
    if enabled:
        app.session_interface = _ResilientSessionInterface(app.session_interface)


def create_app():
    _configure_logging()

    app = Flask(__name__)

    secret_key, db_uri = _resolve_required_config()
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ECHO"] = os.getenv("SQLALCHEMY_ECHO", "false").lower() in ("1", "true", "yes")

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis.from_url(
        redis_url,
        health_check_interval=30,
        socket_keepalive=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True
    # Secure cookies are not stored/sent over plain HTTP; default off in dev so
    # local and LAN (http://127.0.0.1, http://192.168.x.x) keep Redis sessions + CSRF.
    _flask_env = os.getenv("FLASK_ENV", "development").lower()
    _default_session_secure = "true" if _flask_env == "production" else "false"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv(
        "SESSION_COOKIE_SECURE", _default_session_secure
    ).lower() in (
        "1",
        "true",
        "yes",
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    session.init_app(app)
    _install_dev_session_fallback(app)

    app.config["SQLALCHEMY_COMMIT_ON_TEARDOWN"] = True
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 5,
        "max_overflow": 5,
    }

    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "localhost")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com")

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    phase_yaml = resolve_phase_entitlements_path()
    app.extensions["phase_config"] = PhaseEntitlements(phase_yaml)

    # So INFO from app.* (e.g. world generation phases) shows on stderr with flask run.
    _app_log = logging.getLogger("app")
    _app_log.setLevel(logging.INFO)
    if not _app_log.handlers:
        _sh = logging.StreamHandler()
        _sh.setLevel(logging.INFO)
        _sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        _app_log.addHandler(_sh)
    _app_log.propagate = False

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id:
            return None
        with db.session.no_autoflush:
            user = db.session.get(User, int(user_id))
        if not user:
            logger.debug("user_id %s not found in database", user_id)
        return user

    # Compatibility bootstrap: old DBs missing campaign_id columns should still boot.
    #
    # Ordering rules:
    #   1) Helpers that ADD columns referenced by the ORM models (Campaign.current_game_day,
    #      Player.campaign_id, SimulationState.campaign_id, GMWorldState.campaign_id) must run
    #      BEFORE any helper that issues an ORM query against those models. Otherwise the
    #      ORM SELECT lists a non-existent column, the psycopg2 transaction goes into
    #      InFailedSqlTransaction, and every subsequent helper skips with that error.
    #   2) Each except branch rolls back the session so a single failure can't poison the
    #      next helper's preliminary checks.
    def _safe_bootstrap(label, fn, on_applied=None):
        try:
            applied = fn()
            if on_applied is not None:
                on_applied(applied)
        except Exception as exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.warning("%s skipped: %s", label, exc)

    with app.app_context():
        # Stage A — DDL-only legacy compat (no ORM queries against re-keyed models).
        _safe_bootstrap(
            "campaign_scope compatibility bootstrap",
            ensure_campaign_scope_columns,
            warn_if_compat_mode_applied,
        )
        _safe_bootstrap(
            "phase entitlement compatibility bootstrap",
            ensure_phase_entitlement_columns,
            warn_if_phase_compat_applied,
        )
        _safe_bootstrap(
            "user_password_history compatibility bootstrap",
            ensure_user_password_history_table,
            warn_if_password_history_compat_applied,
        )
        _safe_bootstrap(
            "player NPC compatibility bootstrap",
            ensure_player_npc_columns,
            warn_if_player_npc_compat_applied,
        )
        _safe_bootstrap(
            "simulation_state sim_clicks compatibility bootstrap",
            ensure_simulation_state_click_columns,
            warn_if_simulation_state_clicks_applied,
        )
        _safe_bootstrap(
            "ensure_simulation_logs_table",
            ensure_simulation_logs_table,
            warn_if_simulation_logs_table_created,
        )
        _safe_bootstrap(
            "ensure_sim_rules_table",
            ensure_sim_rules_table,
            warn_if_sim_rules_table_created,
        )
        _safe_bootstrap(
            "ensure_deleted_campaign_sim_snapshot_table",
            ensure_deleted_campaign_sim_snapshot_table,
            warn_if_deleted_campaign_sim_snapshot_table_created,
        )
        _safe_bootstrap(
            "ensure_region_campaign_only",
            ensure_region_campaign_only,
            warn_if_region_campaign_only_applied,
        )

        # Stage B — campaign re-key migration. MUST run before ORM-querying helpers
        # (ensure_join_codes_columns) because Campaign.current_game_day and
        # Player.campaign_id are now declared on the ORM models.
        _safe_bootstrap(
            "preflight_campaign_rekey",
            preflight_campaign_rekey,
            warn_if_preflight_applied,
        )
        _safe_bootstrap(
            "ensure_campaign_current_game_day_column",
            ensure_campaign_current_game_day_column,
            warn_if_campaign_current_game_day_applied,
        )
        _safe_bootstrap(
            "ensure_campaign_debt_column",
            ensure_campaign_debt_column,
            warn_if_campaign_debt_column_applied,
        )
        _safe_bootstrap(
            "ensure_simulation_state_campaign_id",
            ensure_simulation_state_campaign_id,
            warn_if_simulation_state_campaign_applied,
        )
        _safe_bootstrap(
            "ensure_gm_world_state_campaign_id",
            ensure_gm_world_state_campaign_id,
            warn_if_gm_world_state_campaign_applied,
        )
        _safe_bootstrap(
            "ensure_player_campaign_id",
            ensure_player_campaign_id,
            warn_if_player_campaign_applied,
        )

        # Stage C — helpers that issue ORM queries against the re-keyed models.
        _safe_bootstrap(
            "solo_player_vault compatibility bootstrap",
            ensure_solo_player_vault_schema,
            warn_if_solo_vault_compat_applied,
        )
        _safe_bootstrap(
            "join_codes compatibility bootstrap",
            ensure_join_codes_columns,
            warn_if_join_codes_compat_applied,
        )

        # Stage D — final cleanup that requires backfills to be complete.
        _safe_bootstrap(
            "drop_campaign_player_table",
            drop_campaign_player_table,
            warn_if_campaign_player_dropped,
        )
        _safe_bootstrap(
            "ensure_world_tables_campaign_only",
            ensure_world_tables_campaign_only,
            warn_if_world_tables_campaign_only_applied,
        )

    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth
    from app.routes.player_routes import player_bp
    from app.routes import gm_routes
    from app.routes.gm_routes import gm_bp
    from app.routes.simulation_routes import simulation_bp
    from app.routes.admin_routes import admin_bp

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(gm_bp)
    app.register_blueprint(player_bp, url_prefix="/player")
    app.register_blueprint(simulation_bp)  # Simulation routes have /api prefix
    app.register_blueprint(admin_bp)

    # JSON simulation API: CSRF via header from dashboard; exempt to avoid token issues on some clients
    csrf.exempt(simulation_bp)
    csrf.exempt(gm_routes.gm_simulation_run_period)
    csrf.exempt(gm_routes.gm_simulation_job_status)
    csrf.exempt(gm_routes.gm_run_simulation_tick)
    csrf.exempt(gm_routes.gm_update_simulation_speed)

    @app.after_request
    def add_no_store_headers(response):
        sensitive_prefixes = (
            "/auth/",
            "/player/",
            "/gm/",
            "/admin/",
            "/campaigns",
            "/home",
        )
        path = request.path if request else ""
        if any(path.startswith(p) for p in sensitive_prefixes):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.errorhandler(404)
    def _not_found(_error):
        return render_template("404.html", message="Not found"), 404

    if app.debug:
        logger.info("Registered routes:")
        for rule in app.url_map.iter_rules():
            logger.info("  %s %s -> %s", sorted(rule.methods or []), rule, rule.endpoint)

    return app


app = create_app()
