import random
from faker import Faker
from app.extensions import db
from app.models.backend import City, Shop, ShopInventory, Item
from app.models.users import GMProfile

# Initialize Faker for realistic-ish names
fake = Faker()

# --- D&D 5e Inspired Data ---
ITEM_TYPES = [
    'Weapon', 'Armor', 'Potion', 'Scroll', 'Ring', 'Wondrous Item',
    'Ammunition', 'Tool', '' # Empty string for miscellaneous
]

ITEM_RARITIES = {
    'Common': {'price_range': (1, 50), 'description_adj': ['simple', 'mundane', 'sturdy', 'plain']},
    'Uncommon': {'price_range': (51, 500), 'description_adj': ['finely crafted', 'well-made', 'unusual', 'gleaming']},
    'Rare': {'price_range': (501, 5000), 'description_adj': ['enchanted', 'magical', 'masterwork', 'ancient']},
    'Very Rare': {'price_range': (5001, 50000), 'description_adj': ['powerful', 'legendary', 'mysterious', 'otherworldly']},
    'Legendary': {'price_range': (50001, 500000), 'description_adj': ['mythic', 'epic', 'artifact-like', 'world-shaking']},
}

WEAPON_NAMES = [
    "Longsword", "Shortsword", "Greatsword", "Dagger", "Scimitar", "Axe", "Greataxe",
    "Mace", "Warhammer", "Light Crossbow", "Shortbow", "Sling", "Spear", "Trident", "Glaive"
]
ARMOR_NAMES = [
    "Leather Armor", "Chain Shirt", "Scale Mail", "Breastplate", "Half Plate", "Full Plate",
    "Shield", "Studded Leather"
]
POTION_NAMES = [
    "Potion of Healing", "Potion of Greater Healing", "Potion of Clairvoyance",
    "Potion of Flying", "Potion of Growth", "Potion of Resistance"
]
SCROLL_NAMES = [
    "Scroll of Fireball", "Scroll of Healing Word", "Scroll of Identify", "Scroll of Comprehend Languages"
]
RING_NAMES = [
    "Ring of Protection", "Ring of Mind Shielding", "Ring of Water Walking"
]
WONDROUS_ITEM_NAMES = [
    "Bag of Holding", "Cloak of Protection", "Boots of Elvenkind", "Orb of Dragonkind"
]
MISC_NAMES = [
    "Rope", "Lantern", "Bedroll", "Torch", "Fishing Tackle", "Climbing Kit"
]

# --- City and Shop Names ---
CITY_PREFIXES = ["Silver", "Iron", "Gold", "River", "Stone", "Wind", "Bright", "Dark", "Whisper", "Star"]
CITY_SUFFIXES = ["wood", "haven", "dale", "burg", "port", "fall", "ridge", "glen", "creek", "shire"]

SHOP_THEMES = {
    "General Store": ["The General Goods Emporium", "Trader's Mart", "The Common Exchange", "Hickory's General Store"],
    "Weapon Shop": ["The Blade & Bow", "Ye Olde Armoury", "Forge & Hammer", "The Warrior's Den"],
    "Armor Shop": ["The Shield & Plate", "Ironclad Outfitters", "The Armored Guard"],
    "Potion Shop": ["The Gilded Goblet", "Elixir & Brew", "The Alchemist's Den", "Whispering Potions"],
    "Magic Shop": ["Arcane Emporium", "The Wizard's Attic", "Mystic Relics", "Scroll & Staff"],
    "Pawn Shop": ["The Lucky Pawn", "Second Chance Goods", "Grubby's Bargains"],
    "Bookstore": ["The Loremaster's Tome", "Ancient Texts", "Whisperwind Library"],
    "Blacksmith": ["The Burning Anvil", "Steel & Spark", "The Master Smithy"],
    "Jeweler": ["Gems & Jewels", "The Shining Stone", "Dragon's Hoard Jewelry"]
}

# --- Seeding Function ---
def seed_gm_data(gm_profile_id, num_cities=10, num_shops_per_city=10, num_global_items=50, num_items_per_shop=10):
    """
    Seeds a GM's world with cities, shops, and items.
    """
    gm_profile = GMProfile.query.get(gm_profile_id)
    if not gm_profile:
        print(f"Error: GM Profile with ID {gm_profile_id} not found.")
        return False

    print(f"Seeding data for GM: {gm_profile.user.username} (ID: {gm_profile_id})")

    # Removed the data clearing logic as per your instruction.
    # New data will be added on top of existing data for this GM.
    # In a production environment, you would typically handle data idempotency
    # or clear data more robustly.
    #
    # Old deletion code (now removed):
    # db.session.query(ShopInventory).join(Shop).filter(
    #     Shop.gm_profile_id == gm_profile_id
    # ).delete(synchronize_session=False)
    # Shop.query.filter_by(gm_profile_id=gm_profile_id).delete(synchronize_session=False)
    # City.query.filter_by(gm_profile_id=gm_profile_id).delete(synchronize_session=False)
    # Item.query.filter_by(gm_profile_id=gm_profile_id).delete(synchronize_session=False)
    # db.session.commit() # This commit would clear data
    # print("Cleared existing data for this GM.") # This print statement would also be removed

    # 1. Create a global pool of unique Items for this GM
    global_items = []
    print(f"Creating {num_global_items} distinct global items... (GM ID: {gm_profile_id})")
    for i in range(num_global_items):
        item_type = random.choice(ITEM_TYPES)
        rarity_name = random.choice(list(ITEM_RARITIES.keys()))
        rarity_data = ITEM_RARITIES[rarity_name]
        
        # Pick a base name based on type
        item_base_name = ""
        if item_type == 'Weapon':
            item_base_name = random.choice(WEAPON_NAMES)
        elif item_type == 'Armor':
            item_base_name = random.choice(ARMOR_NAMES)
        elif item_type == 'Potion':
            item_base_name = random.choice(POTION_NAMES)
        elif item_type == 'Scroll':
            item_base_name = random.choice(SCROLL_NAMES)
        elif item_type == 'Ring':
            item_base_name = random.choice(RING_NAMES)
        elif item_type == 'Wondrous Item':
            item_base_name = random.choice(WONDROUS_ITEM_NAMES)
        else: # For Ammunition, Tool, Misc
            item_base_name = random.choice(MISC_NAMES)

        # Ensure item_base_name is not empty before using it in f-string
        if item_base_name:
            item_name = f"{rarity_name} {item_base_name}"
            description = f"A {random.choice(rarity_data['description_adj'])}, {rarity_name.lower()} {item_base_name.lower()}."
        else:
            item_name = f"{rarity_name} Item {i+1}"
            description = f"A {random.choice(rarity_data['description_adj'])}, {rarity_name.lower()} item."
        
        base_price = random.randint(*rarity_data['price_range'])

        item = Item(
            name=item_name,
            type=item_type,
            rarity=rarity_name,
            description=description,
            base_price=base_price,
            gm_profile_id=gm_profile_id
        )
        global_items.append(item)
        db.session.add(item)
    db.session.commit() # Commit items to get their IDs
    print(f"Created {len(global_items)} global items.")

    # 2. Create Cities
    cities = []
    print(f"Creating {num_cities} cities... (GM ID: {gm_profile_id})")
    for i in range(num_cities):
        city_name = f"{random.choice(CITY_PREFIXES)}{random.choice(CITY_SUFFIXES)}"
        city = City(name=city_name, gm_profile_id=gm_profile_id)
        cities.append(city)
        db.session.add(city)
    db.session.commit() # Commit cities to get their IDs
    print(f"Created {len(cities)} cities.")

    # 3. Create Shops for each City and populate their inventories
    print(f"Creating {num_shops_per_city} shops per city and populating inventories...")
    for city in cities:
        for i in range(num_shops_per_city):
            shop_theme = random.choice(list(SHOP_THEMES.keys()))
            shop_name = random.choice(SHOP_THEMES[shop_theme])
            
            # FIX: Add 'type' to the Shop constructor
            shop = Shop(name=shop_name, type=shop_theme, gm_profile_id=gm_profile_id) 
            db.session.add(shop)
            db.session.flush() # Flush to get shop.shop_id before linking to city

            # Link shop to city
            shop.cities.append(city) 
            
            # Populate shop inventory
            items_for_this_shop = random.sample(global_items, min(num_items_per_shop, len(global_items)))
            for item in items_for_this_shop:
                stock = random.randint(1, 10) # Random stock between 1 and 10
                dynamic_price = int(item.base_price * random.uniform(0.7, 1.3)) # Price fluctuation
                dynamic_price = max(1, dynamic_price) # Ensure price is at least 1

                shop_inventory_entry = ShopInventory(
                    shop_id=shop.shop_id,
                    item_id=item.item_id,
                    stock=stock,
                    dynamic_price=dynamic_price
                )
                db.session.add(shop_inventory_entry)
    
    db.session.commit()
    print("Seeding complete!")
    return True
