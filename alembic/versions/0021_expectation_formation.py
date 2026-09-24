"""Add formation (explicit vs inferred) to expectations.

Existing rows predate the marking: they were all derived from evidenced
turns by the extractor, so backfill as explicit. Companion-authored
tentative intentions from later background/dreaming cognition will write
formation="inferred" with holder=companion; no further schema work needed.
"""
from alembic import op
import sqlalchemy as sa
revision = '0021_expectation_formation'
down_revision = '0020_continuity_policy_owner'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('expectations', sa.Column('formation', sa.String(), nullable=False, server_default='explicit'))
    op.create_index('ix_expectations_formation', 'expectations', ['formation'])

def downgrade():
    op.drop_index('ix_expectations_formation', table_name='expectations')
    op.drop_column('expectations', 'formation')
