import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config.env")

# Print results
print(f"SQLALCHEMY_DATABASE_URI: {os.getenv('SQLALCHEMY_DATABASE_URI')}")
print(f"SECRET_KEY: {os.getenv('SECRET_KEY')}")
print(f"FLASK_ENV: {os.getenv('FLASK_ENV')}")