"""
Player Cities Handler
Handles all city-related business logic for player routes
"""
from flask import render_template, redirect, url_for, flash
from flask_login import current_user
from app.extensions import db
from app.models.users import Player
from app.models.backend import City


def view_cities():
    """View all cities for the player's GM"""
    try:
        # Get the current player
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        # Get all cities for the player's GM
        cities = City.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        
        return render_template('Player_city_view.html', cities=cities)
    except Exception as e:
        print(f"[ERROR] Error viewing cities: {e}")
        flash('An error occurred while viewing cities.', 'error')
        return redirect(url_for('player.player_home'))


def view_city(city_id):
    """View a specific city and its shops"""
    try:
        # Get the current player
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        # Get the city and verify it belongs to the player's GM
        city = City.query.get_or_404(city_id)
        if city.gm_profile_id != player.gm_profile_id:
            flash('You do not have access to this city.', 'error')
            return redirect(url_for('player.player_home'))

        # Get all shops in the city
        shops = city.shops

        return render_template('Player_city_view.html', city=city, shops=shops)
    except Exception as e:
        print(f"[ERROR] Error viewing city: {e}")
        flash('An error occurred while viewing the city.', 'error')
        return redirect(url_for('player.player_home'))
