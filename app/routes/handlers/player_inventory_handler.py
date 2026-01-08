"""
Player Inventory Handler
Handles all inventory-related business logic for player routes
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app.extensions import db
from app.models.users import Player, PlayerInventory
from app.models.backend import Item
from app.routes.handlers.player_helpers import get_current_player


def sell_item(item_id):
    """Sell an item from player's inventory"""
    try:
        # Get the current player
        player, redirect_response = get_current_player()
        if redirect_response:
            return _ajax_or_redirect('Please select a campaign first.', error=True)

        # Get the item and verify it belongs to the player's GM
        item = Item.query.get_or_404(item_id)
        if item.gm_profile_id != player.gm_profile_id:
            return _ajax_or_redirect('You do not have access to this item.', error=True)

        # Get the quantity to sell from the form
        quantity = int(request.form.get('quantity', 1))
        if quantity <= 0:
            return _ajax_or_redirect('Invalid quantity to sell.', error=True)

        # Get the player's inventory entry for this item
        player_inventory = PlayerInventory.query.filter_by(
            player_id=player.id,
            item_id=item_id
        ).first()

        if not player_inventory or player_inventory.quantity < quantity:
            return _ajax_or_redirect('You do not have enough of this item to sell.', error=True)

        # Calculate sell price (50-75% of base price)
        sell_price = int(item.base_price * 0.75)
        total_value = sell_price * quantity

        # Update inventory and currency
        player_inventory.quantity -= quantity
        player.currency += total_value

        if player_inventory.quantity <= 0:
            db.session.delete(player_inventory)

        db.session.commit()

        return _ajax_or_redirect(
            f'Successfully sold {quantity} {item.name} for {total_value} gold!',
            success=True
        )

    except Exception as e:
        print(f"[ERROR] Error selling item: {e}")
        db.session.rollback()
        return _ajax_or_redirect('An error occurred while selling the item.', error=True)


def _ajax_or_redirect(message, success=False, error=False):
    """Helper function to handle AJAX vs regular form responses"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'success' if success else 'error',
            'message': message
        }), 200 if success else 400

    # Fallback for normal HTML forms
    flash(message, 'success' if success else 'error')
    return redirect(request.referrer or url_for('player.player_home'))
