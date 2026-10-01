"""Matter primitive: durable, session-independent coherence layer.

matters (never session-owned; session/message ids are nullable provenance),
matter_links (matter <-> primitive rows) and matter_relations (bounded to
related_to | part_of | depends_on). Entity<->Matter reuses entity_links with
object_type='matter' (no schema change). Downgrade drops all three tables.
"""
from alembic import op
import sqlalchemy as sa
revision = '0032_matters'
down_revision = '0031_consolidation_runs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'matters',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('canonical_key', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('first_seen', sa.DateTime(), nullable=False),
        sa.Column('active_since', sa.DateTime(), nullable=False),
        sa.Column('last_touched', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('merged_into_id', sa.Uuid(), nullable=True),
        sa.Column('summary_entry_id', sa.Uuid(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('formation', sa.String(), nullable=False),
        sa.Column('origin_session_id', sa.String(), nullable=True),
        sa.Column('origin_message_id', sa.String(), nullable=True),
        sa.Column('last_touched_session_id', sa.String(), nullable=True),
        sa.Column('salience_components_json', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('honcho_workspace_id', 'owner_peer_id', 'kind', 'canonical_key',
                'status', 'last_touched', 'merged_into_id'):
        op.create_index(f'ix_matters_{col}', 'matters', [col])

    op.create_table(
        'matter_links',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('matter_id', sa.Uuid(), nullable=False),
        sa.Column('object_type', sa.String(), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('provenance_message_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('matter_id', 'object_type', 'object_id',
                            name='uq_matter_link_object'),
    )
    for col in ('honcho_workspace_id', 'matter_id', 'object_type', 'object_id'):
        op.create_index(f'ix_matter_links_{col}', 'matter_links', [col])
    op.create_index('uq_matter_link_subject', 'matter_links', ['object_type', 'object_id'], unique=True,
                    postgresql_where=sa.text("role = 'subject'"), sqlite_where=sa.text("role = 'subject'"))

    op.create_table(
        'matter_relations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('from_matter_id', sa.Uuid(), nullable=False),
        sa.Column('to_matter_id', sa.Uuid(), nullable=False),
        sa.Column('rel_type', sa.String(), nullable=False),
        sa.Column('evidence_refs_json', sa.String(), nullable=False),
        sa.Column('formation', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("rel_type IN ('related_to','part_of','depends_on')",
                           name='ck_matter_relation_type_bounded'),
    )
    for col in ('honcho_workspace_id', 'from_matter_id', 'to_matter_id'):
        op.create_index(f'ix_matter_relations_{col}', 'matter_relations', [col])
    op.create_index('uq_matter_relation_edge', 'matter_relations',
                    ['honcho_workspace_id', 'from_matter_id', 'to_matter_id', 'rel_type'],
                    unique=True)


def downgrade():
    op.drop_table('matter_relations')
    op.drop_table('matter_links')
    op.drop_table('matters')
