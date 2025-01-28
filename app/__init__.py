import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
from app.extensions import db

# Load environment variables
load_dotenv()

# Initialize extensions (without app)
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # Set configuration from environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'temporary_key_for_testing')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///default.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)

    # Import and register blueprints
    from app.routes.main_routes import main_bp
    from app.routes.city_routes import city_bp
    from app.routes.shop_routes import shop_bp
    from app.routes.item_routes import item_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(city_bp, url_prefix="/cities")
    app.register_blueprint(shop_bp, url_prefix="/shops")
    app.register_blueprint(item_bp, url_prefix="/items")

    # Debug: Print registered routes
    print("Registered Routes:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule}")

    return app

# Create the Flask app instance
app = create_app()
