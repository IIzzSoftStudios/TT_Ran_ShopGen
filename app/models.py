from app import db



class City(db.Model):
    __tablename__ = "cities"

    city_id = db.Column(db.Integer, primary_key=True)  # Primary Key
    name = db.Column(db.String(100), nullable=False, index=True)  # Indexed for fast lookup
    size = db.Column(db.String(50))
    population = db.Column(db.Integer)
    region = db.Column(db.String(100), index=True)  # Indexed for region filtering

    def __repr__(self):
        return f"<City {self.name} (Size: {self.size}, Population: {self.population}, Region: {self.region})>"

