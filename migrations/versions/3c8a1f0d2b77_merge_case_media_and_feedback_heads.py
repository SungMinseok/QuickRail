"""merge case media and feedback heads

Revision ID: 3c8a1f0d2b77
Revises: 17571d3c55ea, 4a6d2c9b7f21
Create Date: 2026-01-08

"""

from alembic import op


revision = '3c8a1f0d2b77'
down_revision = ('17571d3c55ea', '4a6d2c9b7f21')
branch_labels = None
depends_on = None


def upgrade():
    # merge-only migration (no schema changes)
    pass


def downgrade():
    # merge-only migration (no schema changes)
    pass


