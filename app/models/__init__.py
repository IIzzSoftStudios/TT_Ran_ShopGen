# app/models/__init__.py

# Import models from submodules to make them accessible directly from app.models
# The order matters for resolving ForeignKey/relationship dependencies

# Import User first as it's the most fundamental model
from .users import User

# Then import other models that might depend on User
from .backend import City, Shop, Item, ShopInventory, shop_cities
from .users import GMProfile, Player, PlayerInventory
from .market import RegionalMarket, GlobalMarket, DemandModifier, ModifierTarget

# Import production models (if uncommented and used)
# from .production import ResourceNode, ProductionHistory, ResourceTransform

# Import economy models (if uncommented and used)
# from .economy import MarketEvent, PlayerInvestment, ShopMaintenance

# You might need to adjust the import order or handle specific circular dependencies
# if Flask-Migrate or SQLAlchemy throws errors during initialization.

# Define __all__ to control `from app.models import *` behavior (optional but good practice)
__all__ = [
    # users.py (most fundamental)
    'User',
    # backend.py
    'City', 'Shop', 'Item', 'ShopInventory', 'shop_cities',
    # users.py (other models)
    'GMProfile', 'Player', 'PlayerInventory',
    # market.py
    'RegionalMarket', 'GlobalMarket', 'DemandModifier', 'ModifierTarget',
    # production.py
    # 'ResourceNode', 'ProductionHistory', 'ResourceTransform', 
    # economy.py
    # 'MarketEvent', 'PlayerInvestment', 'ShopMaintenance',
]
