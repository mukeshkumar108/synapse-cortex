"""Owner-scope existing suppression and clarification records across chats.

Legacy NULL owners stay session-scoped; never backfill from guesses.
"""
from alembic import op
import sqlalchemy as sa
revision = '0020_continuity_policy_owner'
down_revision = '0019_candidate_receipts'
branch_labels = None
depends_on = None

def upgrade():
    for table in ('suppressions', 'clarification_candidates'):
        op.add_column(table, sa.Column('owner_peer_id', sa.String(), nullable=True))
        op.create_index(f'ix_{table}_owner_peer_id', table, ['owner_peer_id'])

def downgrade():
    for table in ('clarification_candidates', 'suppressions'):
        op.drop_index(f'ix_{table}_owner_peer_id', table_name=table)
        op.drop_column(table, 'owner_peer_id')
