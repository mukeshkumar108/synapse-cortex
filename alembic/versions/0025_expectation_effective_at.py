"""Effective dating on expectations (Step 3B1).

created_at is discovered_at (when Cortex learned it). effective_at is when
the state became true/relevant, set from the grounded temporal window where
known, else message time. Retrospective correction (later discovery that an
expectation existed earlier) backdates effective_at without rewriting
created_at — the distinction the replay demanded.
"""
from alembic import op
import sqlalchemy as sa
revision = '0025_expectation_effective_at'
down_revision = '0024_identity_model_foundation'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('expectations', sa.Column('effective_at', sa.DateTime(), nullable=True))
    op.create_index('ix_expectations_effective_at', 'expectations', ['effective_at'])

def downgrade():
    op.drop_index('ix_expectations_effective_at', table_name='expectations')
    op.drop_column('expectations', 'effective_at')
