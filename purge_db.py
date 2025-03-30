from app import create_app, db
from app.models import (
    City, Shop, Item, ShopInventory, RegionalMarket, GlobalMarket,
    DemandModifier, ModifierTarget, User, GMProfile, Player, PlayerInventory,
    ResourceNode, ProductionHistory, ResourceTransform, MarketEvent,
    PlayerInvestment, ShopMaintenance, SimulationState, SimulationLog, SimRule
)
from sqlalchemy import text

def purge_database():
    app = create_app()
    with app.app_context():
        # Disable foreign key checks temporarily
        db.session.execute(text('SET CONSTRAINTS ALL DEFERRED'))
        
        # First, clear junction tables and tables with foreign key dependencies
        junction_tables = [
            ShopInventory,  # Junction between Shop and Item
            ModifierTarget,  # Junction for DemandModifier
            PlayerInventory,  # Junction between Player and Item
            ProductionHistory,  # Depends on ResourceNode
            PlayerInvestment,  # Depends on Player and Shop
            ShopMaintenance,  # Depends on Shop
            SimulationLog,  # Depends on GMProfile
            SimRule,  # Depends on GMProfile
            RegionalMarket,  # Depends on City and Item
            GlobalMarket,  # Depends on Item
            ResourceNode,  # Depends on City and Player
            ResourceTransform,  # Depends on Item
            MarketEvent,  # Depends on City
        ]
        
        for table in junction_tables:
            try:
                db.session.query(table).delete()
                print(f"Cleared table: {table.__tablename__}")
            except Exception as e:
                print(f"Error clearing table {table.__tablename__}: {str(e)}")
                db.session.rollback()
        
        # Then clear main tables
        main_tables = [
            City, Shop, Item, DemandModifier, User, GMProfile, Player, SimulationState
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