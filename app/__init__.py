import os
import sys
import importlib.util
# #region agent log
try:
    _ws = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".."))
    _log = os.path.join(_ws, "debug-2d6ee8.log")
    _spec = importlib.util.find_spec("flask_wtf")
    with open(_log, "a", encoding="utf-8") as _f:
        _f.write(
            __import__("json").dumps(
                {
                    "sessionId": "2d6ee8",
                    "hypothesisId": "H1_H2",
                    "location": "app/__init__.py:import",
                    "message": "pre-import env and flask_wtf findability",
                    "data": {
                        "executable": sys.executable,
                        "path_count": len(sys.path),
                        "path_sample": sys.path[:3] if len(sys.path) >= 3 else sys.path,
                        "flask_wtf_found": _spec is not None,
                        "cwd": os.getcwd(),
                    },
                    "timestamp": __import__("time").time_ns() // 1_000_000,
                }
            )
            + "\n"
        )
except Exception as _e:
    pass
# #endregion
from flask import Flask
from dotenv import load_dotenv
from app.extensions import db, migrate, bcrypt, login_manager, csrf
from flask.cli import with_appcontext
import click

# Load environment variables
load_dotenv("config.env")

def create_app():
    app = Flask(__name__)

    # Load configuration from environment variables
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY must be set in the environment. "
            "Set it in config.env or your deployment environment."
        )
    app.config["SECRET_KEY"] = secret_key
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI") 
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = True
    
    # Flask's default cookie-based sessions work perfectly with Flask-Login
    # No need for Flask-Session which can cause conflicts

    app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    
    # Initialize database and migration extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Import models after database initialization
    from app.models.users import User
    from app.models.backend import City, Shop, Item, ShopInventory

    @login_manager.user_loader
    def load_user(user_id):
        if not user_id:
            print("DEBUG: No user_id found in session")
            return None
        # Using db.session.get is preferred for primary key lookups
        user = db.session.get(User, int(user_id))
        if not user:
            print(f"DEBUG: User ID {user_id} not found in database")
        return user

    # Register blueprints
    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth
    from app.routes.player_routes import player_bp
    from app.routes.gm_routes import gm_bp
    from app.routes.sim_api_routes import sim_api_bp

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(gm_bp)  # GM routes already have /gm prefix
    app.register_blueprint(player_bp, url_prefix="/player")
    app.register_blueprint(sim_api_bp)

    # Debugging: Print registered routes
    print("\nRegistered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.methods} {rule}")

    # CLI commands
    from app.cli.price_history_cleanup import cleanup_price_history
    from app.cli.price_history_aggregate import aggregate_old_price_history

    @app.cli.command("price-history-cleanup")
    @with_appcontext
    def price_history_cleanup_command():
        """Run a batched cleanup of old PriceHistory rows based on retention config."""
        deleted = cleanup_price_history()
        click.echo(f"Deleted {deleted} PriceHistory rows older than retention window.")

    @app.cli.command("price-history-aggregate-old")
    @with_appcontext
    def price_history_aggregate_old_command():
        """Aggregate very old PriceHistory rows into monthly buckets for long-term trends."""
        groups = aggregate_old_price_history()
        click.echo(f"Created {groups} aggregated monthly price history groups.")

    return app

# Create the Flask app instance
app = create_app()
