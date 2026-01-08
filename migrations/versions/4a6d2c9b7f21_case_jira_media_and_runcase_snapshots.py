"""case jira/media and runcase snapshots

Revision ID: 4a6d2c9b7f21
Revises: 2f1b7d8c9a10
Create Date: 2026-01-08

"""

from alembic import op
import sqlalchemy as sa


revision = '4a6d2c9b7f21'
down_revision = '2f1b7d8c9a10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'case_jira_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(length=800), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_case_jira_links_case_id', 'case_jira_links', ['case_id'])
    op.create_index('ix_case_jira_links_created_at', 'case_jira_links', ['created_at'])

    op.create_table(
        'case_media',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('original_name', sa.String(length=300), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_case_media_case_id', 'case_media', ['case_id'])
    op.create_index('ix_case_media_created_at', 'case_media', ['created_at'])

    op.add_column('run_cases', sa.Column('jira_links_snapshot', sa.Text(), nullable=True))
    op.add_column('run_cases', sa.Column('media_names_snapshot', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('run_cases', 'media_names_snapshot')
    op.drop_column('run_cases', 'jira_links_snapshot')

    op.drop_index('ix_case_media_created_at', table_name='case_media')
    op.drop_index('ix_case_media_case_id', table_name='case_media')
    op.drop_table('case_media')

    op.drop_index('ix_case_jira_links_created_at', table_name='case_jira_links')
    op.drop_index('ix_case_jira_links_case_id', table_name='case_jira_links')
    op.drop_table('case_jira_links')


