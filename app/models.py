from app.extensions import db

class City(db.Model):
    __tablename__ = "cities"
    city_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    size = db.Column(db.String(50))
    population = db.Column(db.Integer)
    region = db.Column(db.String(100), index=True)

    def __repr__(self):
        return f"<City {self.name} (Size: {self.size}, Population: {self.population}, Region: {self.region})>"

class Shop(db.Model):
    __tablename__ = "shops"
    shop_id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)

    city = db.relationship("City", backref="shops")


    def __repr__(self):
        return f"<Shop {self.type} in City {self.city_id}>"
