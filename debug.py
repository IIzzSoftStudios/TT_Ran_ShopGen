# from app import db
# from app.models import City
# print(City)

from dotenv import load_dotenv, find_dotenv
import os

dotenv_path = find_dotenv()
print(f"Using .env file at: {dotenv_path}")
load_dotenv(dotenv_path)

print(f"SECRET_KEY: {os.getenv('SECRET_KEY')}")
print(f"SQLALCHEMY_DATABASE_URI: {os.getenv('SQLALCHEMY_DATABASE_URI')}")
