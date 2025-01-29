"""Add shop_cities table (Many-to-Many relationship between Shops and Cities)

Revision ID: 8aff6839d4ff
Revises: 6a72a1c267f3
Create Date: 2025-01-28 18:30:00.123456

"""
from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic
revision = '8aff6839d4ff'
down_revision = '6a72a1c267f3'  # Make sure this matches the last successful migration
branch_labels = None
depends_on = None


def upgrade():
    """Create the shop_cities table to establish a Many-to-Many relationship."""
    op.create_table(
        'shop_cities',
        sa.Column('shop_id', sa.Integer(), sa.ForeignKey('shops.shop_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('cities.city_id', ondelete='CASCADE'), primary_key=True)
    )


def downgrade():
    """Drop the shop_cities table if rolling back."""
    op.drop_table('shop_cities')
