"""Uttered-at timestamp on commitment candidates (3B2).

Due windows for relative temporal phrases ("tomorrow") must ground to when
the promise was uttered, not when violation is evaluated. Assistant turns do
not write TurnStamps (those feed the user-active guard), so commitments carry
their own anchor, set at upsert from turn time.
"""
from alembic import op
import sqlalchemy as sa
revision = '0027_commitment_uttered_at'
down_revision = '0026_review_and_resolution_evidence'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('commitment_candidates', sa.Column('uttered_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('commitment_candidates', 'uttered_at')
