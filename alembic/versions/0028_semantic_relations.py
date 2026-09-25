"""Phase-B tiny persistence: reified semantic claims + relations.

No role, salience, surface, or authority columns by design (see
src/models/semantic.py). Downgrade drops both tables.
"""
from alembic import op
import sqlalchemy as sa
revision = '0028_semantic_relations'
down_revision = '0027_commitment_uttered_at'
branch_labels = None
depends_on = None

_CLAIM_COLS = [
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('honcho_workspace_id', sa.String(), nullable=False),
    sa.Column('content_hash', sa.String(), nullable=False),
    sa.Column('content', sa.String(), nullable=False),
    sa.Column('subjects_json', sa.String(), nullable=False),
    sa.Column('evidence_refs_json', sa.String(), nullable=False),
    sa.Column('formation', sa.String(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('effective_at', sa.DateTime(), nullable=True),
    sa.Column('discovered_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('honcho_workspace_id', 'content_hash',
                        name='uq_semantic_claim_workspace_hash'),
]

_RELATION_COLS = [
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('honcho_workspace_id', sa.String(), nullable=False),
    sa.Column('rel_type', sa.String(), nullable=False),
    sa.Column('from_claim_id', sa.Uuid(), nullable=False),
    sa.Column('to_claim_id', sa.Uuid(), nullable=False),
    sa.Column('evidence_refs_json', sa.String(), nullable=False),
    sa.Column('formation', sa.String(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('effective_at', sa.DateTime(), nullable=True),
    sa.Column('discovered_at', sa.DateTime(), nullable=True),
    sa.Column('last_corroborated_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('superseded_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['from_claim_id'], ['semantic_claims.id']),
    sa.ForeignKeyConstraint(['to_claim_id'], ['semantic_claims.id']),
    sa.CheckConstraint(
        "rel_type IN ('same_as','refines','contradicts','supersedes',"
        "'depends_on','part_of','conditioned_on','fulfils',"
        "'partially_fulfils','resolves','reopens','enables','blocks')",
        name='ck_semantic_relation_type_bounded',
    ),
]

_RELATION_INDEXES = [
    'honcho_workspace_id', 'rel_type', 'from_claim_id', 'to_claim_id',
    'status', 'superseded_by_id',
]

def upgrade():
    op.create_table('semantic_claims', *_CLAIM_COLS)
    for col in ('honcho_workspace_id', 'content_hash'):
        op.create_index(f'ix_semantic_claims_{col}', 'semantic_claims', [col])
    op.create_table('semantic_relations', *_RELATION_COLS)
    for col in _RELATION_INDEXES:
        op.create_index(f'ix_semantic_relations_{col}', 'semantic_relations', [col])

def downgrade():
    for col in reversed(_RELATION_INDEXES):
        op.drop_index(f'ix_semantic_relations_{col}', table_name='semantic_relations')
    op.drop_table('semantic_relations')
    for col in ('content_hash', 'honcho_workspace_id'):
        op.drop_index(f'ix_semantic_claims_{col}', table_name='semantic_claims')
    op.drop_table('semantic_claims')
