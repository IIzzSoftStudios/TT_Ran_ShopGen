from .extensions import db
from app import create_app
from sqlalchemy import inspect, text
import sys

def purge_all_data():
    """
    Deletes all data from all tables while preserving schema.
    Great for dev resets. Keeps migrations and structure.
    """
    # Ask for confirmation
    print("\n⚠️  WARNING: This will delete ALL data from ALL tables!")
    print("This operation cannot be undone!")
    confirmation = input("\nType 'YES' to confirm: ")
    
    if confirmation != 'YES':
        print("Operation cancelled.")
        return

    with db.engine.connect() as conn:
        trans = conn.begin()
        try:
            inspector = inspect(conn)
            table_names = inspector.get_table_names()
            
            if not table_names:
                print("No tables found in the database.")
                return

            print(f"\nFound {len(table_names)} tables to purge...")

            # Disable FK constraints temporarily
            dialect = db.engine.dialect.name
            if dialect == 'sqlite':
                conn.execute(text("PRAGMA foreign_keys = OFF"))
            elif dialect == 'postgresql':
                conn.execute(text("SET session_replication_role = 'replica'"))
            elif dialect == 'mysql':
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

            for table in table_names:
                try:
                    print(f"Purging {table}...")
                    conn.execute(text(f'DELETE FROM "{table}"'))
                except Exception as e:
                    print(f"Warning: Could not purge table {table}: {str(e)}")
                    continue

            # Re-enable FK checks
            if dialect == 'sqlite':
                conn.execute(text("PRAGMA foreign_keys = ON"))
            elif dialect == 'postgresql':
                conn.execute(text("SET session_replication_role = 'origin'"))
            elif dialect == 'mysql':
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

            trans.commit()
            print("\n✅ Success: All data purged while preserving table structures.")

        except Exception as e:
            trans.rollback()
            print(f"\n❌ Error: Failed to purge data: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        purge_all_data()
