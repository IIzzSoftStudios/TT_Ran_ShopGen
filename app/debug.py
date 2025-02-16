from app import create_app, db  # Import your app creation logic and db instance

# Create the application and activate the context
app = create_app()

with app.app_context():
    # Clear any cached data and ensure the session starts fresh
    db.session.expire_all()
    db.session.rollback()  # Roll back any ongoing transactions
    db.session.close()     # Close and reset the session

    print("[DEBUG] Cleared session cache, reset connections.")
