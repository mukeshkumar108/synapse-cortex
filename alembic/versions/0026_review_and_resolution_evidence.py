"""Review flag on suppressions; resolution evidence on commitments (3B2).

suppressions.review_note: model-judged direction/conflict notes. A review
flag is a worklist signal for lifecycle review — it never blocks, writes,
or retires anything by itself.
commitments.resolution_evidence: where fulfilment/violation evidence lives
when derived. Absence of a row here plus an elapsed due condition is what
makes a violation derivable without silent fulfil/discard.
"""
from alembic import op
import sqlalchemy as sa
revision = '0026_review_and_resolution_evidence'
down_revision = '0025_expectation_effective_at'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('suppressions', sa.Column('review_note', sa.String(), nullable=True))
    op.add_column('commitment_candidates', sa.Column('resolution_evidence', sa.String(), nullable=True))

def downgrade():
    op.drop_column('commitment_candidates', 'resolution_evidence')
    op.drop_column('suppressions', 'review_note')
