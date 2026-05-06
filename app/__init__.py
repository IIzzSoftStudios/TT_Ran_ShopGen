import logging
import os
from flask import Flask, request
from dotenv import load_dotenv
from app.extensions import db, migrate, bcrypt, login_manager, session, csrf, mail, limiter
from app.models import User
from app.services.schema_compat import (
    ensure_campaign_scope_columns,
    ensure_phase_entitlement_columns,
    ensure_player_npc_columns,
    ensure_join_codes_columns,
    ensure_user_password_history_table,
    warn_if_compat_mode_applied,
    warn_if_phase_compat_applied,
    warn_if_password_history_compat_applied,
    warn_if_player_npc_compat_applied,
    warn_if_join_codes_compat_applied,
)
from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path

# Load environment variables
load_dotenv("config.env")


def create_app():
    app = Flask(__name__)

    # Load configuration from environment variables
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "temporary_key_for_testing")
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI") 
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = True
    

    # Ensure Flask uses sessions properly
    app.config['SESSION_TYPE'] = "filesystem"  
    app.config['SESSION_PERMANENT'] = False
    app.config["SESSION_USE_SIGNER"] = True
    app.config["SESSION_FILE_THRESHOLD"] = 100  # Limits excessive session files

    session.init_app(app)

    app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "localhost")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com")

    # Initialize database and migration extensions
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
            print("DEBUG: No user_id found in session")
            return None
        with db.session.no_autoflush:
            user = db.session.get(User, int(user_id))
        if not user:
            print(f"DEBUG: User ID {user_id} not found in database") 
        return user
    
    # Import models to ensure they are registered
    from app.models import City, Shop, Item, ShopInventory

    # Compatibility bootstrap: old DBs missing campaign_id columns should still boot.
    with app.app_context():
        try:
            patched_any = ensure_campaign_scope_columns()
            warn_if_compat_mode_applied(patched_any)
        except Exception as exc:
            app.logger.warning("campaign_scope compatibility bootstrap skipped: %s", exc)
        try:
            patched_phase = ensure_phase_entitlement_columns()
            warn_if_phase_compat_applied(patched_phase)
        except Exception as exc:
            app.logger.warning("phase entitlement compatibility bootstrap skipped: %s", exc)
        try:
            patched_pwh = ensure_user_password_history_table()
            warn_if_password_history_compat_applied(patched_pwh)
        except Exception as exc:
            app.logger.warning("user_password_history compatibility bootstrap skipped: %s", exc)
        try:
            patched_npc = ensure_player_npc_columns()
            warn_if_player_npc_compat_applied(patched_npc)
        except Exception as exc:
            app.logger.warning("player NPC compatibility bootstrap skipped: %s", exc)
        try:
            patched_join = ensure_join_codes_columns()
            warn_if_join_codes_compat_applied(patched_join)
        except Exception as exc:
            app.logger.warning("join_codes compatibility bootstrap skipped: %s", exc)

    # Register blueprints
    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth
    from app.routes.player_routes import player_bp
    from app.routes import gm_routes
    from app.routes.gm_routes import gm_bp
    from app.routes.simulation_routes import simulation_bp
    from app.routes.admin_routes import admin_bp

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(gm_bp)  # GM routes already have /gm prefix
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

    # Debugging: Print registered routes
    print("\nRegistered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.methods} {rule}")

    return app

# Create the Flask app instance
app = create_app()
