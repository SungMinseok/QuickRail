"""Add feedback attachments

Revision ID: d7f411e2bc32
Revises: da5d4adfbbfd
Create Date: 2026-01-07 13:07:13.943198

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7f411e2bc32'
down_revision = 'da5d4adfbbfd'
branch_labels = None
depends_on = None


def upgrade():
    """피드백 첨부 테이블만 추가.

    이 프로젝트는 운영 DB 상태가 100% 동일하지 않은 케이스가 있어,
    autogenerate가 무관한 FK/constraint 변경을 함께 감지할 수 있습니다.
    따라서 이 revision은 feedback_attachments만 안전하게(존재 시 스킵) 생성합니다.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('feedback_attachments'):
        op.create_table(
            'feedback_attachments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('file_path', sa.String(length=600), nullable=False),
            sa.Column('original_name', sa.String(length=300), nullable=False),
            sa.Column('mime_type', sa.String(length=120), nullable=True),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('uploaded_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['post_id'], ['feedback_posts.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    idx_names = set()
    if insp.has_table('feedback_attachments'):
        try:
            idx_names = {i.get('name') for i in (insp.get_indexes('feedback_attachments') or []) if i.get('name')}
        except Exception:
            idx_names = set()

    indexes = [
        ('ix_feedback_attachments_created_at', ['created_at']),
        ('ix_feedback_attachments_post_id', ['post_id']),
        ('ix_feedback_attachments_uploaded_by', ['uploaded_by']),
    ]
    for name, cols in indexes:
        if name not in idx_names:
            op.create_index(name, 'feedback_attachments', cols, unique=False)


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table('feedback_attachments'):
        return

    try:
        idx_names = {i.get('name') for i in (insp.get_indexes('feedback_attachments') or []) if i.get('name')}
    except Exception:
        idx_names = set()

    for name in [
        'ix_feedback_attachments_uploaded_by',
        'ix_feedback_attachments_post_id',
        'ix_feedback_attachments_created_at',
    ]:
        if name in idx_names:
            op.drop_index(name, table_name='feedback_attachments')

    op.drop_table('feedback_attachments')



