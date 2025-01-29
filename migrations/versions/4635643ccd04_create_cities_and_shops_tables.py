"""Create cities, shops, and shop_cities tables.

Revision ID: 4635643ccd04
Revises: 
Create Date: 2025-01-27 20:53:00.122411

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4635643ccd04'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create cities table
    op.create_table(
        'cities',
        sa.Column('city_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('size', sa.String(length=50), nullable=True),
        sa.Column('population', sa.Integer(), nullable=True),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('city_id')
    )
    op.create_index('ix_cities_name', 'cities', ['name'], unique=False)
    op.create_index('ix_cities_region', 'cities', ['region'], unique=False)

    # Create shops table
    op.create_table(
        'shops',
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('city_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['city_id'], ['cities.city_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('shop_id')
    )

    # Create shop_cities table for many-to-many relationship
    op.create_table(
        'shop_cities',
        sa.Column('shop_id', sa.Integer(), sa.ForeignKey('shops.shop_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('cities.city_id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    # Drop shop_cities table first (since it has foreign keys)
    op.drop_table('shop_cities')

    # Drop shops table
    op.drop_table('shops')

    # Drop indexes before dropping cities table
    op.drop_index('ix_cities_region', table_name='cities')
    op.drop_index('ix_cities_name', table_name='cities')

    # Drop cities table
    op.drop_table('cities')
