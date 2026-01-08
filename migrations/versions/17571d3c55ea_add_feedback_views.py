"""Add feedback views

Revision ID: 17571d3c55ea
Revises: d7f411e2bc32
Create Date: 2026-01-07 13:47:10.374458

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '17571d3c55ea'
down_revision = 'd7f411e2bc32'
branch_labels = None
depends_on = None


def upgrade():
    """피드백 조회수(유저당 1회) 지원.

    주의:
    - 프로젝트 DB 상태에 따라 autogenerate가 무관한 FK/constraint 변경을 감지할 수 있어
      이 revision은 피드백 관련 스키마만 안전하게 적용합니다.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    # 1) feedback_post_views 테이블
    if not insp.has_table('feedback_post_views'):
        op.create_table(
            'feedback_post_views',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['post_id'], ['feedback_posts.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('post_id', 'user_id', name='uq_feedback_post_view_post_user'),
        )

    # 인덱스 보정
    idx_names = set()
    try:
        idx_names = {i.get('name') for i in (insp.get_indexes('feedback_post_views') or []) if i.get('name')}
    except Exception:
        idx_names = set()
    for name, cols in [
        ('ix_feedback_post_views_created_at', ['created_at']),
        ('ix_feedback_post_views_post_id', ['post_id']),
        ('ix_feedback_post_views_user_id', ['user_id']),
    ]:
        if name not in idx_names:
            op.create_index(name, 'feedback_post_views', cols, unique=False)

    # 2) feedback_posts.view_count 컬럼 (기본 0)
    cols = {c.get('name') for c in (insp.get_columns('feedback_posts') or [])}
    if 'view_count' not in cols:
        op.add_column(
            'feedback_posts',
            sa.Column('view_count', sa.Integer(), nullable=False, server_default=sa.text('0'))
        )
    # 인덱스 보정
    try:
        post_idx_names = {i.get('name') for i in (insp.get_indexes('feedback_posts') or []) if i.get('name')}
    except Exception:
        post_idx_names = set()
    if 'ix_feedback_posts_view_count' not in post_idx_names:
        op.create_index('ix_feedback_posts_view_count', 'feedback_posts', ['view_count'], unique=False)


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if insp.has_table('feedback_posts'):
        try:
            post_idx_names = {i.get('name') for i in (insp.get_indexes('feedback_posts') or []) if i.get('name')}
        except Exception:
            post_idx_names = set()
        if 'ix_feedback_posts_view_count' in post_idx_names:
            op.drop_index('ix_feedback_posts_view_count', table_name='feedback_posts')

        cols = {c.get('name') for c in (insp.get_columns('feedback_posts') or [])}
        if 'view_count' in cols:
            op.drop_column('feedback_posts', 'view_count')

    if insp.has_table('feedback_post_views'):
        try:
            idx_names = {i.get('name') for i in (insp.get_indexes('feedback_post_views') or []) if i.get('name')}
        except Exception:
            idx_names = set()
        for name in [
            'ix_feedback_post_views_user_id',
            'ix_feedback_post_views_post_id',
            'ix_feedback_post_views_created_at',
        ]:
            if name in idx_names:
                op.drop_index(name, table_name='feedback_post_views')

        op.drop_table('feedback_post_views')



