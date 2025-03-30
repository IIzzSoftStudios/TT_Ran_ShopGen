from app.extensions import db
from datetime import datetime

class ResourceNode(db.Model):
    __tablename__ = 'resource_nodes'
    
    node_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    production_rate = db.Column(db.Float, nullable=False)
    quality = db.Column(db.Float, nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.city_id'))
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    gm_profile_id = db.Column(db.Integer, db.ForeignKey('gm_profile.id'))
    
    # Add relationship to Item
    item_id = db.Column(db.Integer, db.ForeignKey('items.item_id'))
    item = db.relationship('Item', backref='resource_nodes')
    
    # Relationships
    city = db.relationship('City', backref='resource_nodes')
    owner = db.relationship('User', backref='owned_resource_nodes')
    gm_profile = db.relationship('GMProfile', backref='resource_nodes')
    
    def __repr__(self):
        return f'<ResourceNode {self.name}>' 