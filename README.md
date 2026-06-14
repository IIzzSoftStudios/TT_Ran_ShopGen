# Econo-Forge

## Overview
**Econo-Forge** is a campaign economy tool for tabletop GMs. It replaces spreadsheet shop tracking with a SQL-backed system where shops restock, prices react to stock, and market days advance from one GM hub.

The project is built with **Python, PostgreSQL, and Flask**, with player dashboards for browsing shops, inventory, and character gear in the same campaign economy.

## Features
### **Game Master Interface**
- Dashboard for managing regions, cities, shops, items, players/NPCs, maps, encounters, and compendiums.
- Tools for world generation, player setup, and running market-day simulations from both Simulation and Market Overview panels.
- Item folders, bulk catalog actions, manual shop stocking, OGL-safe D&D 5e starter item templates, and campaign-scoped item/world compendiums.
- Dynamic pricing based on stock levels, rarity, demand modifiers, and configurable market volatility.

### **Player Interface**
- View personal funds and inventory on the player dashboard.
- Browse shops by city and region from the integrated shop browse panel.
- Buy and sell items with stock reflected across the campaign.
- Review D&D 5e class spell options from the player Spells tab, even before specific spells are selected on the sheet.

### **Dynamic Pricing & Inventory Management**
- Item prices fluctuate based on stock levels, rarity, and demand modifiers.
- Each simulation tick (one game day) runs bounded price-elasticity **daily sales**, then recalculates prices from updated stock.
- Shops **restock on a per-shop schedule**, with replenishment scaled by city size (`data/shop_roll_catalog.yaml`).
- World generation builds a **procedural item pool** and stocks shops from that pool.
- Campaign market volatility (`0` stable to `10` wild) scales demand and price event randomness on future ticks.

### **Database Structure**
- **Cities**, **Shops**, **Items**, and **Shop Inventory** tables power the shared campaign economy.
- **Registration keys** gate account creation in early-access deployments.

## Documentation
- In-app docs: `/docs` (getting started, GM hub, player guide, changelog, roadmap).
- Deployment notes: `deploy/README.md`, `DOCKER.md`, `config.example.env`.
