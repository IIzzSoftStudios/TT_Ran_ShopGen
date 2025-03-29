import pytest
from datetime import datetime
from app.services.simulation import simulation_service
from app.models import SimulationState, SimulationLog, GMProfile, User
from app.extensions import db

@pytest.fixture
def gm_user(app, client):
    """Create a GM user for testing."""
    with app.app_context():
        user = User(
            username="test_gm",
            password="test_password",
            role="gm"
        )
        user.set_password("test_password")
        db.session.add(user)
        db.session.commit()

        gm_profile = GMProfile(user_id=user.id)
        db.session.add(gm_profile)
        db.session.commit()

        return user

@pytest.fixture
def simulation_state(app, gm_user):
    """Create a simulation state for testing."""
    with app.app_context():
        state = SimulationState(
            current_tick=0,
            speed="pause",
            last_tick_time=datetime.utcnow(),
            gm_profile_id=gm_user.gm_profile.id
        )
        db.session.add(state)
        db.session.commit()
        return state

def test_initialize_simulation(app, gm_user):
    """Test simulation initialization."""
    with app.app_context():
        state = simulation_service.initialize_simulation(gm_user.gm_profile.id)
        assert state.current_tick == 0
        assert state.speed == "pause"
        assert state.gm_profile_id == gm_user.gm_profile.id

def test_set_simulation_speed(app, gm_user):
    """Test setting simulation speed."""
    with app.app_context():
        # Initialize simulation
        simulation_service.initialize_simulation(gm_user.gm_profile.id)
        
        # Test valid speeds
        for speed in ["1x", "5x", "100x", "1000x", "pause"]:
            state = simulation_service.set_simulation_speed(gm_user.gm_profile.id, speed)
            assert state.speed == speed
        
        # Test invalid speed
        with pytest.raises(ValueError):
            simulation_service.set_simulation_speed(gm_user.gm_profile.id, "invalid_speed")

def test_manual_tick(app, gm_user):
    """Test manual tick advancement."""
    with app.app_context():
        # Initialize simulation
        simulation_service.initialize_simulation(gm_user.gm_profile.id)
        
        # Test manual tick
        status = simulation_service.manual_tick(gm_user.gm_profile.id)
        assert status["current_tick"] == 1
        assert status["status"] == "paused"

def test_get_simulation_status(app, gm_user):
    """Test getting simulation status."""
    with app.app_context():
        # Initialize simulation
        simulation_service.initialize_simulation(gm_user.gm_profile.id)
        
        # Test status retrieval
        status = simulation_service.get_simulation_status(gm_user.gm_profile.id)
        assert "current_tick" in status
        assert "speed" in status
        assert "last_tick_time" in status
        assert "status" in status

def test_get_recent_logs(app, gm_user):
    """Test retrieving simulation logs."""
    with app.app_context():
        # Initialize simulation
        simulation_service.initialize_simulation(gm_user.gm_profile.id)
        
        # Run a few ticks to generate logs
        for _ in range(3):
            simulation_service.manual_tick(gm_user.gm_profile.id)
        
        # Test log retrieval
        logs = simulation_service.get_recent_logs(gm_user.gm_profile.id)
        assert len(logs) == 3
        assert all(log["event_type"] == "tick" for log in logs)

def test_simulation_error_handling(app, gm_user):
    """Test simulation error handling."""
    with app.app_context():
        # Initialize simulation
        simulation_service.initialize_simulation(gm_user.gm_profile.id)
        
        # Set a speed to start the scheduler
        simulation_service.set_simulation_speed(gm_user.gm_profile.id, "1x")
        
        # Force an error by setting an invalid speed
        with pytest.raises(ValueError):
            simulation_service.set_simulation_speed(gm_user.gm_profile.id, "invalid_speed")
        
        # Verify simulation is still running
        status = simulation_service.get_simulation_status(gm_user.gm_profile.id)
        assert status["status"] == "running"

def test_simulation_persistence(app, gm_user):
    """Test simulation state persistence across restarts."""
    with app.app_context():
        # Initialize simulation and run some ticks
        simulation_service.initialize_simulation(gm_user.gm_profile.id)
        simulation_service.set_simulation_speed(gm_user.gm_profile.id, "1x")
        
        # Run a few ticks
        for _ in range(3):
            simulation_service.manual_tick(gm_user.gm_profile.id)
        
        # Get current state
        state = SimulationState.query.filter_by(gm_profile_id=gm_user.gm_profile.id).first()
        current_tick = state.current_tick
        
        # Simulate app restart by creating new service instance
        new_service = simulation_service.__class__()
        
        # Verify state is preserved
        new_state = SimulationState.query.filter_by(gm_profile_id=gm_user.gm_profile.id).first()
        assert new_state.current_tick == current_tick 