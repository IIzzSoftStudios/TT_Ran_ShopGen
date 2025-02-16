import os
from flask import Flask
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from app.extensions import db 

# Load environment variables
load_dotenv("config.env")

# Initialize Flask extensions globally
db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # Load configuration from environment variables
    app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "temporary_key_for_testing")
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI") 
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Debugging: Print loaded config
    print(f"[DEBUG] SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"[DEBUG] SECRET_KEY: {app.config['SECRET_KEY']}")

    # Initialize database and migration extensions
    db.init_app(app)
    migrate.init_app(app, db)  # FIXED: Migrate should be global

    # Import models to ensure they are registered
    from app.models import City, Shop, Item, ShopInventory

    # Register blueprints
    from app.routes.main_routes import main_bp
    from app.routes.city_routes import city_bp
    from app.routes.shop_routes import shop_bp
    from app.routes.item_routes import item_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(city_bp, url_prefix="/cities")
    app.register_blueprint(shop_bp, url_prefix="/shops")
    app.register_blueprint(item_bp, url_prefix="/items")

    # Debugging: Print registered routes
    print("Registered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")

    return app

# Create the Flask app instance
app = create_app()
