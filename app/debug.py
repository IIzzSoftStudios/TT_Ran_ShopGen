import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config.env")

# Only indicate presence/absence of secrets in development; never print actual values
if os.getenv("FLASK_ENV") == "development":
    print(f"SQLALCHEMY_DATABASE_URI present: {bool(os.getenv('SQLALCHEMY_DATABASE_URI'))}")
    print(f"SECRET_KEY present: {bool(os.getenv('SECRET_KEY'))}")
    print(f"FLASK_ENV: {os.getenv('FLASK_ENV')}")