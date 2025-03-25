from app.extensions import db
from app.models import City, GMProfile, User
from flask import Flask
from sqlalchemy import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://game_master:GM!@localhost/shopgen'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    # Check if there are any GM profiles
    gm_profiles = GMProfile.query.all()
    print(f"Found {len(gm_profiles)} GM profiles")
    
    if not gm_profiles:
        print("No GM profiles found. Please create a GM user first.")
        exit(1)
    
    # Get the first GM profile to use as default
    default_gm = gm_profiles[0]
    print(f"Using GM profile with ID {default_gm.id} as default")
    
    # Check current cities
    cities = City.query.all()
    print(f"Found {len(cities)} cities")
    
    # Check current column state
    result = db.session.execute(text("SELECT column_name, is_nullable, data_type FROM information_schema.columns WHERE table_name = 'cities' AND column_name = 'gm_profile_id';"))
    column_info = result.fetchone()
    print(f"Column info: {column_info}")
    
    if column_info:
        print("Updating existing cities with default GM profile...")
        # Update any NULL gm_profile_id values
        db.session.execute(text(f"UPDATE cities SET gm_profile_id = {default_gm.id} WHERE gm_profile_id IS NULL;"))
        # Make the column NOT NULL
        db.session.execute(text("ALTER TABLE cities ALTER COLUMN gm_profile_id SET NOT NULL;"))
        db.session.commit()
        print("Cities updated successfully!")
    else:
        print("gm_profile_id column not found in cities table") 