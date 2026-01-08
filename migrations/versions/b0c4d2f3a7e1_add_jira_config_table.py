"""Add Jira config table

Revision ID: b0c4d2f3a7e1
Revises: 6234e33713d0
Create Date: 2026-01-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0c4d2f3a7e1'
down_revision = '6234e33713d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'jira_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('base_url', sa.String(length=300), nullable=True),
        sa.Column('email', sa.String(length=200), nullable=True),
        sa.Column('api_token', sa.String(length=500), nullable=True),
        sa.Column('project_key', sa.String(length=50), nullable=True),
        sa.Column('issue_type', sa.String(length=100), nullable=True),
        sa.Column('default_components', sa.String(length=500), nullable=True),
        sa.Column('default_labels', sa.String(length=500), nullable=True),
        sa.Column('default_priority', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('jira_configs')


