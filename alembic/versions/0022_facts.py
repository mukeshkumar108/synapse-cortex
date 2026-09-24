"""Durable holder-scoped fact store (Step 3 Slice 2).

Health states, biographical facts, grief history and vocation are settled
content, never expectations. Facts never participate in supersession,
outcome lifecycle or violation derivation.
"""
from alembic import op
import sqlalchemy as sa
revision = '0022_facts'
down_revision = '0021_expectation_formation'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'facts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('candidate_key', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('evidence_verbatim', sa.String(), nullable=False),
        sa.Column('formation', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('honcho_workspace_id', 'honcho_session_id', 'honcho_message_id', 'owner_peer_id', 'category'):
        op.create_index(f'ix_facts_{col}', 'facts', [col])

def downgrade():
    for col in ('category', 'owner_peer_id', 'honcho_message_id', 'honcho_session_id', 'honcho_workspace_id'):
        op.drop_index(f'ix_facts_{col}', table_name='facts')
    op.drop_table('facts')
