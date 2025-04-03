import os
from flask import Flask
from dotenv import load_dotenv
from app.extensions import db, migrate, bcrypt, login_manager, session
from app.models import User

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
    
    # Initialize database and migration extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

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

    # Register blueprints
    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth
    from app.routes.player_routes import player_bp
    from app.routes.gm_routes import gm_bp

    app.register_blueprint(auth, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(gm_bp)  # GM routes already have /gm prefix
    app.register_blueprint(player_bp, url_prefix="/player")

    # Debugging: Print registered routes
    print("\nRegistered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.methods} {rule}")

    return app

# Create the Flask app instance
app = create_app()
