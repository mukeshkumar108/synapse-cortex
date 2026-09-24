"""Explicit invited flag on open loops (Step 3 contract tightening).

The 'explicitly invited' property was encoded by magic title text
("Invited follow-up"), which forced vague titles and broke the moment titles
carried the model's own words. Now a real column; old rows backfilled.
"""
from alembic import op
import sqlalchemy as sa
revision = '0023_open_loop_invited'
down_revision = '0022_facts'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('open_loops', sa.Column('invited', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE open_loops SET invited = TRUE WHERE title = 'Invited follow-up'")

def downgrade():
    op.drop_column('open_loops', 'invited')
