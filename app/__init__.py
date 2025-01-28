import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

# Load .env file from the root directory
load_dotenv()

app = Flask(__name__)
print(f"App instance created. SECRET_KEY: {app.config['SECRET_KEY']}")


# Set the secret key from .env
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://Game_Master:887441Lf!@localhost/Shop Generator'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Import routes to avoid circular imports
from app import routes


print(f"Loaded SECRET_KEY: {os.getenv('SECRET_KEY')}")
