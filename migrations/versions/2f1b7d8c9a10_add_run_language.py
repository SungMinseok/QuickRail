"""add run language

Revision ID: 2f1b7d8c9a10
Revises: 9c2f3e1a4d11
Create Date: 2026-01-06

"""

from alembic import op
import sqlalchemy as sa


revision = '2f1b7d8c9a10'
down_revision = '9c2f3e1a4d11'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('runs', sa.Column('language', sa.String(length=10), nullable=True))


def downgrade():
    op.drop_column('runs', 'language')


