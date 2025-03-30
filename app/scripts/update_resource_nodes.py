import os
import sys
import logging

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import create_app, db
from app.models import ResourceNode, Item

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_resource_nodes():
    """Update resource nodes with appropriate items based on their type."""
    app = create_app()
    with app.app_context():
        # Get all resource nodes
        nodes = ResourceNode.query.all()
        logger.info(f"Found {len(nodes)} resource nodes to process")

        # Get all items
        items = Item.query.all()
        logger.info(f"Found {len(items)} items")

        # Define mapping of resource node types to item types
        type_mapping = {
            'mine': ['material', 'tool'],
            'forest': ['material', 'tool'],
            'fishery': ['potion', 'material'],  # Food-like items would be potions or materials
            'farm': ['potion', 'material'],     # Food-like items would be potions or materials
            'quarry': ['material']
        }

        # Process each node
        for node in nodes:
            logger.info(f"Processing node {node.node_id}: {node.name} (Type: {node.type})")
            
            # Skip if node already has an item
            if node.item_id is not None:
                logger.info(f"Node {node.node_id} already has item {node.item_id}")
                continue

            # Get valid item types for this node
            valid_types = type_mapping.get(node.type, [])
            if not valid_types:
                logger.warning(f"No item type mapping found for resource node type: {node.type}")
                continue

            # Find a suitable item
            suitable_items = [i for i in items if i.type in valid_types]
            if not suitable_items:
                logger.warning(f"No suitable items found for node {node.name} (Type: {node.type})")
                continue

            # Assign the first suitable item
            node.item_id = suitable_items[0].item_id
            logger.info(f"Assigned item {suitable_items[0].name} (ID: {suitable_items[0].item_id}) to node {node.name}")

        try:
            db.session.commit()
            logger.info("Successfully updated resource nodes")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating resource nodes: {e}")

if __name__ == "__main__":
    update_resource_nodes() 