from app.extensions import db
from app import create_app
from sqlalchemy import inspect, text

def purge_all_data():
    """
    Deletes all data from all tables while preserving schema.
    Great for dev resets. Keeps migrations and structure.
    """
    with db.engine.connect() as conn:
        trans = conn.begin()
        try:
            inspector = inspect(conn)
            table_names = inspector.get_table_names()

            # Disable FK constraints temporarily (for PostgreSQL or SQLite)
            if db.engine.dialect.name == 'sqlite':
                conn.execute(text("PRAGMA foreign_keys = OFF"))
            elif db.engine.dialect.name == 'postgresql':
                conn.execute(text("SET session_replication_role = 'replica'"))

            for table in table_names:
                print(f"Purging {table}...")
                conn.execute(text(f'DELETE FROM "{table}"'))


            # Re-enable FK checks
            if db.engine.dialect.name == 'sqlite':
                conn.execute(text("PRAGMA foreign_keys = ON"))
            elif db.engine.dialect.name == 'postgresql':
                conn.execute(text("SET session_replication_role = 'origin'"))

            trans.commit()
            print("✅ All data purged (tables intact).")

        except Exception as e:
            trans.rollback()
            print(f"❌ Failed to purge: {e}")
            raise

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        purge_all_data()
