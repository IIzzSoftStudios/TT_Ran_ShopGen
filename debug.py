from sqlalchemy import inspect
from app import db

with db.engine.connect() as connection:
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    print("Tables:", tables)
