"""
GM Simulation Handler
Handles all simulation-related business logic for GM routes
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app.services.logging_config import gm_logger
from app.services.simulation import SimulationEngine
from app.scripts.seeder import seed_gm_data
from app.extensions import db
from datetime import datetime


def _debug_request(request_type: str, route: str):
    """Debug helper for request logging."""
    simulation_engine = SimulationEngine()
    gm_logger.debug(
        f"{request_type} request to {route}:\n"
        f"  Method: {request.method}\n"
        f"  Form data: {request.form}\n"
        f"  Args: {request.args}\n"
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}"
    )


def home():
    """Render the GM dashboard with simulation controls and status."""
    simulation_engine = SimulationEngine()
    _debug_request("GET", "/gm/")
    
    # Check if we should run a tick based on current speed
    if simulation_engine.should_run_tick():
        try:
            stats = simulation_engine.run_tick(current_user.gm_profile.id)
            flash(
                f"Simulation tick completed: Updated {stats['shops_updated']} shops "
                f"and {stats['items_updated']} items.",
                "success"
            )
        except Exception as e:
            flash(f"Error during simulation tick: {str(e)}", "danger")
    
    # Log current simulation state
    gm_logger.debug(
        f"GM dashboard state:\n"
        f"  User ID: {current_user.gm_profile.id}\n"
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}\n"
        f"  Time since last tick: {datetime.now() - simulation_engine.last_tick_time}"
    )
    
    return render_template(
        "GM_Home.html",
        current_tick=0,  # Will be stored in database
        current_speed=simulation_engine.current_speed,
        last_tick_time=simulation_engine.last_tick_time,
        simulation_status="active" if simulation_engine.current_speed != "pause" else "paused"
    )


def seed_world():
    """Route to trigger the seeding of the GM's world data."""
    simulation_engine = SimulationEngine()
    _debug_request("POST", "/gm/seed_world")
    
    # current_user.gm_profile is already guaranteed to exist by @gm_bp.before_request
    gm_profile = current_user.gm_profile

    try:
        # Call the seeding function with the GM's profile ID
        success = seed_gm_data(
            gm_profile.id,
            num_cities=10,
            num_shops_per_city=10,
            num_global_items=75, # Global distinct items to choose from
            num_items_per_shop=10 # Items assigned to each shop
        )
        if success:
            flash("Your world has been successfully seeded!", "success")
        else:
            flash("Failed to seed world. Check server logs for details.", "error")
    except Exception as e:
        db.session.rollback() # Ensure rollback on error
        gm_logger.error(f"Error during seeding world: {str(e)}", exc_info=True)
        flash(f"An error occurred during seeding: {str(e)}", "error")

    # Redirect back to the GM home page (dashboard)
    return redirect(url_for("gm.gm_home"))


def run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard."""
    simulation_engine = SimulationEngine()
    _debug_request("POST", "/gm/simulation/tick")
    
    try:
        stats = simulation_engine.run_tick(current_user.gm_profile.id)
        
        # Log the tick execution
        gm_logger.debug(
            f"Manual tick execution:\n"
            f"  User ID: {current_user.gm_profile.id}\n"
            f"  Shops updated: {stats['shops_updated']}\n"
            f"  Items updated: {stats['items_updated']}\n"
            f"  Last tick time: {simulation_engine.last_tick_time}\n"
            f"  Time since last tick: {datetime.now() - simulation_engine.last_tick_time}"
        )
        
        return jsonify({
            "status": "success",
            "message": f"Simulation tick completed: Updated {stats['shops_updated']} shops and {stats['items_updated']} items.",
            "stats": stats
        })
        
    except Exception as e:
        gm_logger.error(f"Error during simulation tick: {str(e)}")
        flash(f"Error during simulation tick: {str(e)}", "danger")
    
    return redirect(url_for("gm.gm_home"))


def update_simulation_speed():
    """Update the simulation speed setting and run the appropriate time period."""
    simulation_engine = SimulationEngine()
    _debug_request("POST", "/gm/simulation/speed")
    
    try:
        speed = request.form.get("speed", "pause")
        
        # Map speed to time period
        speed_to_period = {
            "1x": "hour",
            "5x": "day",
            "100x": "week",
            "1000x": "month"
        }
        
        if speed == "pause":
            simulation_engine.set_speed(speed)
            flash("Simulation paused", "info")
        else:
            time_period = speed_to_period.get(speed)
            if not time_period:
                raise ValueError(f"Invalid speed setting: {speed}")
                
            # Run the simulation for the selected time period
            stats = simulation_engine.run_time_period(current_user.gm_profile.id, time_period)
            
            # Log the simulation results
            gm_logger.debug(
                f"Time period simulation completed:\n"
                f"  Period: {time_period}\n"
                f"  Ticks completed: {stats['ticks_completed']}\n"
                f"  Shops updated: {stats['shops_updated']}\n"
                f"  Items updated: {stats['items_updated']}\n"
                f"  Duration: {stats['total_duration']:.2f}s"
            )
            
            flash(
                f"Simulated {time_period}: Updated {stats['shops_updated']} shops "
                f"and {stats['items_updated']} items in {stats['total_duration']:.2f}s",
                "success"
            )
        
    except Exception as e:
        gm_logger.error(f"Error during simulation: {str(e)}")
        flash(f"Error during simulation: {str(e)}", "danger")
    
    return redirect(url_for("gm.gm_home"))


def debug_form():
    """Debug form submission"""
    print("FORM KEYS:", request.form.keys())
    print("FORM DICT:", request.form.to_dict(flat=False))
    return "Check logs"
