"""Add feedback posts

Revision ID: da5d4adfbbfd
Revises: 2f1b7d8c9a10
Create Date: 2026-01-07 11:25:18.244639

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da5d4adfbbfd'
down_revision = '2f1b7d8c9a10'
branch_labels = None
depends_on = None


def upgrade():
    """피드백/공지 게시판 테이블만 추가.

    주의:
    - 이 프로젝트는 운영 중 DB가 alembic_version과 완전히 동기화되어 있지 않은 케이스가 있어,
      자동 생성(migrate)이 다른 테이블까지 함께 감지하는 일이 있었습니다.
    - 따라서 이 revision은 'feedback_posts'만 안전하게(존재 시 스킵) 생성하도록 제한합니다.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('feedback_posts'):
        op.create_table(
            'feedback_posts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=300), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=30), nullable=False),
            sa.Column('is_notice', sa.Boolean(), nullable=False),
            sa.Column('is_admin_only', sa.Boolean(), nullable=False),
            sa.Column('created_by', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id')
        )

    # 인덱스는 테이블이 이미 존재하는 경우(부분 적용 등)에도 누락될 수 있어 보정
    idx_names = set()
    if insp.has_table('feedback_posts'):
        try:
            idx_names = {i.get('name') for i in (insp.get_indexes('feedback_posts') or []) if i.get('name')}
        except Exception:
            idx_names = set()

    indexes = [
        ('ix_feedback_posts_created_at', ['created_at']),
        ('ix_feedback_posts_created_by', ['created_by']),
        ('ix_feedback_posts_is_admin_only', ['is_admin_only']),
        ('ix_feedback_posts_is_notice', ['is_notice']),
        ('ix_feedback_posts_status', ['status']),
        ('ix_feedback_posts_updated_at', ['updated_at']),
    ]
    for name, cols in indexes:
        if name not in idx_names:
            op.create_index(name, 'feedback_posts', cols, unique=False)


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('feedback_posts'):
        return

    try:
        idx_names = {i.get('name') for i in (insp.get_indexes('feedback_posts') or []) if i.get('name')}
    except Exception:
        idx_names = set()

    for name in [
        'ix_feedback_posts_updated_at',
        'ix_feedback_posts_status',
        'ix_feedback_posts_is_notice',
        'ix_feedback_posts_is_admin_only',
        'ix_feedback_posts_created_by',
        'ix_feedback_posts_created_at',
    ]:
        if name in idx_names:
            op.drop_index(name, table_name='feedback_posts')

    op.drop_table('feedback_posts')



