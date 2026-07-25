import json
import logging
import os
import sys
import tempfile

import redis
from dotenv import load_dotenv
from flask import Flask, request, render_template, url_for
from flask_login import current_user
from flask.sessions import SecureCookieSession, SecureCookieSessionInterface

from app.extensions import db, migrate, bcrypt, login_manager, session, csrf, mail, limiter
from app.models import User
from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path
from app.services.schema_compat import (
    drop_campaign_player_table,
    ensure_battle_tables,
    ensure_campaign_debt_column,
    ensure_campaign_current_game_day_column,
    ensure_campaign_scope_columns,
    ensure_deleted_campaign_sim_snapshot_table,
    ensure_gm_world_state_campaign_id,
    ensure_global_market_baseline_stock_column,
    ensure_item_folder_schema,
    ensure_item_srd_columns,
    ensure_monster_srd_columns,
    ensure_monster_known_to_players_column,
    ensure_join_codes_columns,
    ensure_campaign_code_redemption_table,
    ensure_demo_analytics_event_table,
    ensure_expansion_interest_table,
    ensure_stripe_billing_schema,
    ensure_map_tables,
    ensure_phase_entitlement_columns,
    ensure_player_campaign_id,
    ensure_player_gm_meta_columns,
    ensure_player_npc_columns,
    ensure_city_shop_owner_columns,
    ensure_player_npc_notes_table,
    ensure_player_monster_journal_table,
    ensure_region_campaign_only,
    ensure_region_nation_columns,
    ensure_sim_rules_table,
    ensure_simulation_logs_table,
    ensure_simulation_state_campaign_id,
    ensure_simulation_state_click_columns,
    ensure_solo_player_vault_schema,
    ensure_user_password_history_table,
    ensure_user_avatar_column,
    ensure_user_submissions_table,
    ensure_shop_next_restock_day_column,
    ensure_world_tables_campaign_only,
    preflight_campaign_rekey,
    warn_if_battle_tables_created,
    warn_if_campaign_current_game_day_applied,
    warn_if_campaign_debt_column_applied,
    warn_if_campaign_player_dropped,
    warn_if_compat_mode_applied,
    warn_if_deleted_campaign_sim_snapshot_table_created,
    warn_if_gm_world_state_campaign_applied,
    warn_if_global_market_baseline_stock_applied,
    warn_if_item_folder_compat_applied,
    warn_if_item_srd_compat_applied,
    warn_if_monster_srd_compat_applied,
    warn_if_monster_known_to_players_applied,
    warn_if_join_codes_compat_applied,
    warn_if_campaign_code_redemption_table_applied,
    warn_if_demo_analytics_event_table_applied,
    warn_if_expansion_interest_table_applied,
    warn_if_stripe_billing_schema_applied,
    warn_if_password_history_compat_applied,
    warn_if_user_avatar_column_applied,
    warn_if_user_submissions_table_applied,
    warn_if_map_tables_created,
    warn_if_phase_compat_applied,
    warn_if_player_campaign_applied,
    warn_if_player_npc_compat_applied,
    warn_if_player_gm_meta_columns_applied,
    warn_if_city_shop_owner_columns_applied,
    warn_if_player_npc_notes_table_applied,
    warn_if_player_monster_journal_table_applied,
    warn_if_preflight_applied,
    warn_if_region_campaign_only_applied,
    warn_if_region_nation_columns_applied,
    warn_if_sim_rules_table_created,
    warn_if_simulation_logs_table_created,
    warn_if_simulation_state_campaign_applied,
    warn_if_simulation_state_clicks_applied,
    warn_if_solo_vault_compat_applied,
    warn_if_shop_next_restock_day_applied,
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
    """Hard fail-fast in production if required env is missing.

    Cloud Run will mark the revision unhealthy on `sys.exit(1)` and refuse to
    roll forward, which is the desired behavior vs. silently serving with a
    placeholder secret. ``REDIS_URL`` is required because the session backend,
    Flask-Limiter, distributed locks, the Celery broker, and the Celery result
    backend all read it; a missing value would silently fall through to the
    ``redis://localhost:6379/0`` default, which on Cloud Run resolves to the
    container's own loopback (no Redis listening) and breaks every sim path.

    When ``TRSG_CLOUD_RUN_MIGRATE`` is true (Cloud Build migrate job), Redis is
    not required: sessions use filesystem storage and the limiter uses memory.
    """
    flask_env = os.getenv("FLASK_ENV", "development").lower()
    secret_key = os.getenv("SECRET_KEY")
    db_uri = os.getenv("SQLALCHEMY_DATABASE_URI")
    redis_url = os.getenv("REDIS_URL")
    migrate_job = os.getenv("TRSG_CLOUD_RUN_MIGRATE", "").lower() in ("1", "true", "yes")

    if flask_env == "production":
        required = [
            ("SECRET_KEY", secret_key),
            ("SQLALCHEMY_DATABASE_URI", db_uri),
        ]
        if not migrate_job:
            required.append(("REDIS_URL", redis_url))
        missing = [name for name, value in required if not value]
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

    migrate_job = os.getenv("TRSG_CLOUD_RUN_MIGRATE", "").lower() in ("1", "true", "yes")
    test_fs_session = os.getenv("TRSG_TEST_FILESYSTEM_SESSION", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if migrate_job:
        # One-shot Cloud Run Job: no VPC Redis required; only DB + ORM bootstrap run.
        _session_dir = "/tmp/.flask_session_migrate"
        os.makedirs(_session_dir, exist_ok=True)
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = _session_dir
    elif test_fs_session:
        _session_dir = tempfile.mkdtemp(prefix="trsg_pytest_sess_")
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = _session_dir
    else:
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
    # SQLite (e.g. in-memory pytest) rejects pool_size / max_overflow / pool_timeout.
    _is_sqlite = (db_uri or "").lower().startswith("sqlite")
    if _is_sqlite:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    else:
        # Connection pool sizing is split by deployment role so a Celery worker
        # holding connections for an entire 365-tick Year cannot starve the web
        # tier (or vice versa). Cloud Run web revisions are short-lived and
        # request-bound; Celery workers are long-lived and hold connections per
        # in-flight task. Effective ceiling per role:
        #     web:    DB_POOL_SIZE  + DB_MAX_OVERFLOW
        #     worker: DB_POOL_SIZE  + DB_MAX_OVERFLOW
        # Operator must keep
        #   (web_max_instances * gunicorn_workers * web_pool_total)
        #     + (worker_vms * worker_concurrency * worker_pool_total)
        # under the Cloud SQL tier `max_connections`. See deploy/README.md.
        _is_celery_worker = os.getenv("TRSG_ROLE", "").lower() == "worker" or bool(
            os.getenv("CELERY_WORKER_RUNNING")
        )
        if _is_celery_worker:
            _default_pool_size = "2"
            _default_max_overflow = "2"
        else:
            _default_pool_size = "5"
            _default_max_overflow = "5"
        _pool_size = int(os.getenv("DB_POOL_SIZE", _default_pool_size))
        _max_overflow = int(os.getenv("DB_MAX_OVERFLOW", _default_max_overflow))
        _pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))
        _pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": _pool_recycle,
            "pool_size": _pool_size,
            "max_overflow": _max_overflow,
            "pool_timeout": _pool_timeout,
        }

    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "localhost")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com")
    app.config["INVESTOR_DECK_NOTIFY_EMAIL"] = os.getenv(
        "INVESTOR_DECK_NOTIFY_EMAIL", "iizzsoftstudios@gmail.com"
    )
    app.config["CREATOR_PARTNERSHIP_NOTIFY_EMAIL"] = os.getenv(
        "CREATOR_PARTNERSHIP_NOTIFY_EMAIL", "iizzsoftstudios@gmail.com"
    )
    # Public Demo (landing Try Demo → /demo). Snapshot file is required at runtime.
    # [Dev][Web]
    app.config["DEMO_SNAPSHOT_PATH"] = (
        os.getenv("DEMO_SNAPSHOT_PATH") or ""
    ).strip()
    # Optional: campaign id used only by scripts/export_demo_snapshot.py
    # [Dev]
    app.config["DEMO_TEMPLATE_CAMPAIGN_ID"] = (
        os.getenv("DEMO_TEMPLATE_CAMPAIGN_ID") or ""
    ).strip()

    # Pytest and Cloud Build run the full suite in one process with in-memory
    # limiter storage (TRSG_TEST_FILESYSTEM_SESSION). Shared counters cause 429s.
    if os.getenv("TRSG_TEST_FILESYSTEM_SESSION", "").lower() in ("1", "true", "yes"):
        app.config["RATELIMIT_ENABLED"] = False

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

    # GCP readiness: runtime DDL on every process start is a serverless anti-pattern.
    # Cloud Run scale-out can spawn N concurrent instances issuing DDL/SELECT against
    # Cloud SQL, producing connection storms and delayed `$PORT` listening that the
    # platform interprets as unhealthy. In production, schema is assumed at rest; run
    # `scripts/init_schema.py` and `scripts/apply_sql_migrations.py` from a dedicated
    # one-shot job (Cloud Build pre-deploy step or operator-run container) before
    # promoting traffic. The break-glass env `RUN_BOOTSTRAP_IN_PROD=true` re-enables
    # the bootstrap path for an explicit recovery window.
    _flask_env_for_bootstrap = os.getenv("FLASK_ENV", "development").lower()
    _bootstrap_opt_in = os.getenv("RUN_BOOTSTRAP_IN_PROD", "false").lower() in ("1", "true", "yes")
    _skip_bootstrap = _flask_env_for_bootstrap == "production" and not _bootstrap_opt_in

    if _skip_bootstrap:
        app.logger.info(
            "Skipping runtime schema_compat bootstrap (FLASK_ENV=production); "
            "migrations must run via scripts/init_schema.py or scripts/apply_sql_migrations.py "
            "before deploy. Set RUN_BOOTSTRAP_IN_PROD=true to override."
        )

    if not _skip_bootstrap:
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
                "user avatar column compatibility bootstrap",
                ensure_user_avatar_column,
                warn_if_user_avatar_column_applied,
            )
            _safe_bootstrap(
                "user_submissions table compatibility bootstrap",
                ensure_user_submissions_table,
                warn_if_user_submissions_table_applied,
            )
            _safe_bootstrap(
                "expansion_interest table compatibility bootstrap",
                ensure_expansion_interest_table,
                warn_if_expansion_interest_table_applied,
            )
            _safe_bootstrap(
                "demo_analytics_event table compatibility bootstrap",
                ensure_demo_analytics_event_table,
                warn_if_demo_analytics_event_table_applied,
            )
            _safe_bootstrap(
                "campaign_code_redemption table compatibility bootstrap",
                ensure_campaign_code_redemption_table,
                warn_if_campaign_code_redemption_table_applied,
            )
            _safe_bootstrap(
                "stripe billing schema compatibility bootstrap",
                ensure_stripe_billing_schema,
                warn_if_stripe_billing_schema_applied,
            )
            _safe_bootstrap(
                "player NPC compatibility bootstrap",
                ensure_player_npc_columns,
                warn_if_player_npc_compat_applied,
            )
            _safe_bootstrap(
                "item SRD lineage columns compatibility bootstrap",
                ensure_item_srd_columns,
                warn_if_item_srd_compat_applied,
            )
            _safe_bootstrap(
                "monster SRD lineage column compatibility bootstrap",
                ensure_monster_srd_columns,
                warn_if_monster_srd_compat_applied,
            )
            _safe_bootstrap(
                "monster known_to_players column compatibility bootstrap",
                ensure_monster_known_to_players_column,
                warn_if_monster_known_to_players_applied,
            )
            _safe_bootstrap(
                "item folders schema compatibility bootstrap",
                ensure_item_folder_schema,
                warn_if_item_folder_compat_applied,
            )
            _safe_bootstrap(
                "simulation_state sim_clicks compatibility bootstrap",
                ensure_simulation_state_click_columns,
                warn_if_simulation_state_clicks_applied,
            )
            _safe_bootstrap(
                "global_markets baseline_avg_stock + simulation_state.last_market_run",
                ensure_global_market_baseline_stock_column,
                warn_if_global_market_baseline_stock_applied,
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
            _safe_bootstrap(
                "ensure_region_nation_columns",
                ensure_region_nation_columns,
                warn_if_region_nation_columns_applied,
            )
            _safe_bootstrap(
                "ensure_player_gm_meta_columns",
                ensure_player_gm_meta_columns,
                warn_if_player_gm_meta_columns_applied,
            )
            _safe_bootstrap(
                "ensure_city_shop_owner_columns",
                ensure_city_shop_owner_columns,
                warn_if_city_shop_owner_columns_applied,
            )
            _safe_bootstrap(
                "ensure_player_npc_notes_table",
                ensure_player_npc_notes_table,
                warn_if_player_npc_notes_table_applied,
            )
            _safe_bootstrap(
                "ensure_player_monster_journal_table",
                ensure_player_monster_journal_table,
                warn_if_player_monster_journal_table_applied,
            )

            # Stage B — campaign re-key migration.
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
                "ensure_shop_next_restock_day_column",
                ensure_shop_next_restock_day_column,
                warn_if_shop_next_restock_day_applied,
            )
            _safe_bootstrap(
                "ensure_world_tables_campaign_only",
                ensure_world_tables_campaign_only,
                warn_if_world_tables_campaign_only_applied,
            )
            _safe_bootstrap(
                "ensure_map_tables",
                ensure_map_tables,
                warn_if_map_tables_created,
            )
            # Battle tables FK onto map_canvas, so this must run after
            # ensure_map_tables.
            _safe_bootstrap(
                "ensure_battle_tables",
                ensure_battle_tables,
                warn_if_battle_tables_created,
            )

    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth
    from app.routes.player_routes import player_bp
    from app.routes.gm_routes import gm_bp
    from app.routes.simulation_routes import simulation_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.combat_routes import combat_bp
    from app.routes.demo_routes import demo_bp
    from app.routes.billing_routes import billing_bp

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(gm_bp)
    app.register_blueprint(player_bp, url_prefix="/player")
    app.register_blueprint(combat_bp, url_prefix="/api/combat")
    app.register_blueprint(simulation_bp)  # Simulation routes have /api prefix
    app.register_blueprint(admin_bp)

    # JSON simulation API: rely on Flask-WTF's `X-CSRFToken` header validation
    # (configured via WTF_CSRF_HEADERS, includes X-CSRFToken by default). The
    # GM dashboard injects the token on every simulation POST. GET endpoints
    # are inherently safe and stay covered by the header check on writes.
    #
    # Sensitive POSTs we DO NOT exempt (formerly were):
    #   - simulation_bp (POST /api/simulation/{tick,speed})
    #   - gm.gm_simulation_run_period (POST /gm/simulation/run-period)
    #   - gm.gm_run_simulation_tick   (POST /gm/simulation/tick)
    #   - gm.gm_update_simulation_speed (POST /gm/simulation/speed)
    # gm.gm_simulation_job_status is a GET only and needs no CSRF.
    #
    # If a non-browser client (curl, Cloud Scheduler) ever needs to call these,
    # use a separate token-authenticated route family rather than re-exempting
    # session-authenticated endpoints from CSRF.
    app.config.setdefault(
        "WTF_CSRF_HEADERS", ["X-CSRFToken", "X-CSRF-Token", "X-Csrf-Token"]
    )

    @app.before_request
    def block_lapsed_subscription_mutations():
        from app.services.subscription_gate import maybe_block_lapsed_mutation

        return maybe_block_lapsed_mutation()

    @app.context_processor
    def inject_account_menu_context():
        from flask import session as flask_session

        from app.constants.submission_categories import categories_for_json
        from app.services.account_stats import get_campaign_counts
        from app.services.demo_session import active_demo_mode_for_user
        from app.services.subscription_gate import (
            resubscribe_cta_url,
            subscription_lapsed_for_request,
        )

        show_account_menu = False
        account_menu_config = {}
        subscription_lapsed = False
        subscription_lapsed_cta_url = None
        if getattr(current_user, "is_authenticated", False) and request.endpoint:
            if not request.endpoint.startswith("auth.") and not request.endpoint.startswith(
                "static"
            ):
                show_account_menu = True
                counts = get_campaign_counts(current_user)
                mode = flask_session.get("session_mode")
                submitted_as = "Account hub" if mode is None else str(mode).upper()
                account_menu_config = {
                    "submission_categories": categories_for_json(),
                    "submission_post_url": url_for("auth.account_submissions"),
                    "avatar_post_url": url_for("auth.account_avatar"),
                    "avatar_get_url": url_for("auth.account_avatar"),
                    "submitted_as": submitted_as,
                    "gm_count": counts["gm"],
                    "player_count": counts["player"],
                    "is_vault_keeper": getattr(current_user, "role", "") == "vault_keeper",
                    "campaigns_url": url_for("main.campaigns"),
                    "billing_url": url_for("billing.billing_settings"),
                    "logout_url": url_for("auth.logout"),
                }
                # Billing/subscribe pages stay interactive so users can renew.
                on_billing = request.endpoint.startswith("billing.")
                if (
                    not on_billing
                    and not active_demo_mode_for_user(current_user)
                    and subscription_lapsed_for_request()
                ):
                    subscription_lapsed = True
                    subscription_lapsed_cta_url = resubscribe_cta_url()
        return {
            "show_account_menu": show_account_menu,
            "account_menu_config": account_menu_config,
            "subscription_lapsed": subscription_lapsed,
            "subscription_lapsed_cta_url": subscription_lapsed_cta_url,
            "gm_panel_embed": request.args.get("embed") == "1"
            or (request.method == "POST" and request.form.get("embed") == "1"),
        }

    @app.after_request
    def add_no_store_headers(response):
        sensitive_prefixes = (
            "/auth/",
            "/player/",
            "/gm/",
            "/admin/",
            "/campaigns",
            "/home",
            "/demo",
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
