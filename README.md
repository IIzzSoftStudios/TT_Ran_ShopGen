# TT Ran Shop Gen

## Overview
**TT Ran Shop Gen** is a dynamic and scalable **Tabletop RPG Shop Generator** designed to replace slow and complex Google Sheets setups with a robust SQL-backed system. This tool allows Game Masters (GMs) to generate shops with dynamic inventory and pricing based on various in-game factors such as city size, item rarity, and supply-demand trends.

The project is built using **Python, PostgreSQL, and Flask**, with a potential **React-based** companion app for real-time player interactions.

## Features
### **Game Master Interface**
- Dashboard for managing cities, shops, and inventory.
- Tools for adding new items, updating stock, and running inventory simulations.
- Dynamic event system for adjusting prices based on shortages, festivals, or economic changes.

### **Player Interface (In Progress)**
- View personal funds and inventory.
- Navigate cities, browse shop inventories, and search/filter items by price, rarity, or category.
- Track item availability across multiple shops.

### **Dynamic Pricing & Inventory Management**
- Item prices fluctuate based on stock levels, rarity, and demand.
- Shops restock periodically, influenced by city size and economic factors.
- Events (e.g., war, trade booms, supply shortages) dynamically affect item availability.

### **Database Structure**
- **Cities Table**: Stores city details such as size, population, and economy type.
- **Shops Table**: Contains shop types (e.g., weaponsmith, apothecary) and their locations.
- **Items Table**: A centralized database of items with categories, rarity levels, and base pricing.
- **Shop Inventory Table**: Manages item stock, pricing adjustments, and availability per shop.
- **Player Inventory Table**: Tracks player-owned items and funds.
- **Pricing Log (Optional)**: Logs price changes over time for analysis.

## Technologies Used
- **Backend:** Flask (Python), PostgreSQL (SQLAlchemy ORM)
- **Frontend:** HTML, CSS (Future: React for an enhanced player interface)
- **Authentication:** Secure login system with hashed passwords and user roles (Game Master, Player)
- **Deployment:** To be determined (Potential options: AWS, DigitalOcean, or Heroku)