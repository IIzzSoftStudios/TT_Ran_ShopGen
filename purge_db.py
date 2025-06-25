from sqlalchemy import text
from app import create_app, db
from app.models import (
    City, Shop, Item, ShopInventory, RegionalMarket, GlobalMarket,
    DemandModifier, ModifierTarget, User, GMProfile, Player, PlayerInventory,
    shop_cities
)

def purge_database():
    app = create_app()
    with app.app_context():
        # Disable foreign key checks temporarily
        db.session.execute(text('SET CONSTRAINTS ALL DEFERRED'))

        # Clear junction tables and related tables first
        junction_tables = [
            ShopInventory,
            ModifierTarget,
            PlayerInventory,
            RegionalMarket,
            GlobalMarket,
        ]

        # Clear the shop_cities junction table first
        try:
            db.session.execute(text('DELETE FROM shop_cities'))
            print("Cleared table: shop_cities")
        except Exception as e:
            print(f"Error clearing table shop_cities: {str(e)}")
            db.session.rollback()

        for table in junction_tables:
            try:
                db.session.query(table).delete()
                print(f"Cleared table: {table.__tablename__}")
            except Exception as e:
                print(f"Error clearing table {table.__tablename__}: {str(e)}")
                db.session.rollback()

        # Then clear main tables in the correct order
        main_tables = [
            City, Shop, Item, DemandModifier, GMProfile,
            User, Player
        ]

        for table in main_tables:
            try:
                db.session.query(table).delete()
                print(f"Cleared table: {table.__tablename__}")
            except Exception as e:
                print(f"Error clearing table {table.__tablename__}: {str(e)}")
                db.session.rollback()

        # Re-enable foreign key checks
        db.session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))

        # Commit the changes
        db.session.commit()
        print("Database purge completed successfully!")

if __name__ == "__main__":
    purge_database()
