"""Epistemic envelope on model_entries + actor direction on lifecycle primitives.

Nullable/defaulted column adds only: no drops, no data rewrite. Direction on
attention candidates / work items is derived from `kind` / `owner` and needs no
column (services/actor_direction.py).
"""
from alembic import op
import sqlalchemy as sa
revision = '0033_epistemic_direction'
down_revision = '0032_matters'
branch_labels = None
depends_on = None

_MODEL_ENTRY_COLS = [
    ('claim_kind', sa.Column('claim_kind', sa.String(), nullable=True)),
    ('subject_matter_id', sa.Column('subject_matter_id', sa.Uuid(), nullable=True)),
    ('epistemic_status', sa.Column('epistemic_status', sa.String(), nullable=False,
                                   server_default='current')),
    ('evidence_refs_json', sa.Column('evidence_refs_json', sa.String(), nullable=False,
                                     server_default='[]')),
    ('holder_actor', sa.Column('holder_actor', sa.String(), nullable=True)),
    ('direction', sa.Column('direction', sa.String(), nullable=True)),
]
_DIRECTION_TABLES = ('expectations', 'open_loops', 'commitment_candidates')


def upgrade():
    for _, col in _MODEL_ENTRY_COLS:
        op.add_column('model_entries', col)
    op.create_index('ix_model_entries_claim_kind', 'model_entries', ['claim_kind'])
    op.create_index('ix_model_entries_subject_matter_id', 'model_entries', ['subject_matter_id'])
    op.create_index('ix_model_entries_direction', 'model_entries', ['direction'])
    for table in _DIRECTION_TABLES:
        op.add_column(table, sa.Column('direction', sa.String(), nullable=True))
        op.create_index(f'ix_{table}_direction', table, ['direction'])


def downgrade():
    for table in _DIRECTION_TABLES:
        op.drop_index(f'ix_{table}_direction', table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column('direction')
    op.drop_index('ix_model_entries_direction', table_name='model_entries')
    op.drop_index('ix_model_entries_subject_matter_id', table_name='model_entries')
    op.drop_index('ix_model_entries_claim_kind', table_name='model_entries')
    with op.batch_alter_table('model_entries') as batch:
        for name, _ in reversed(_MODEL_ENTRY_COLS):
            batch.drop_column(name)
