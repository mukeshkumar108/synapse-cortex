"""Step 3A identity/model foundation: entities, edges, model entries, links, frames.

Identity substrate for the seven primitives — not a primitive. Entities give
rows a stable referent (owner/holder/subject/target/beneficiary); relationship
edges carry structure; model_entries implement the User/Character/Relationship
Model primitive; turn_frames records per-turn speaking stance for resolution
scoping (3D scene work consumes it later).
"""
from alembic import op
import sqlalchemy as sa
revision = '0024_identity_model_foundation'
down_revision = '0023_open_loop_invited'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'entities',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('frame_scope', sa.String(), nullable=True),
        sa.Column('first_seen_message_id', sa.String(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('provisional', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_entities_workspace', 'entities', ['honcho_workspace_id'])
    op.create_table(
        'entity_aliases',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('entity_id', sa.Uuid(), nullable=False),
        sa.Column('alias', sa.String(), nullable=False),
        sa.Column('provenance_message_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # Deliberately NO unique constraint on (alias, frame): two explicit
    # Marcos in one frame must be able to remain two entities.
    op.create_index('ix_entity_aliases_alias', 'entity_aliases', ['alias'])
    op.create_index('ix_entity_aliases_entity', 'entity_aliases', ['entity_id'])
    op.create_table(
        'relationship_edges',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('from_entity_id', sa.Uuid(), nullable=False),
        sa.Column('to_entity_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('provenance_message_id', sa.String(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('effective_at', sa.DateTime(), nullable=True),
        sa.Column('end_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_relationship_edges_workspace', 'relationship_edges', ['honcho_workspace_id'])
    op.create_table(
        'model_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('owner_peer_id', sa.String(), nullable=True),
        sa.Column('subject_entity_id', sa.Uuid(), nullable=True),
        sa.Column('model_kind', sa.String(), nullable=False),
        sa.Column('claim', sa.String(), nullable=False),
        sa.Column('evidence_verbatim', sa.String(), nullable=False),
        sa.Column('formation', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('effective_at', sa.DateTime(), nullable=True),
        sa.Column('discovered_at', sa.DateTime(), nullable=False),
        sa.Column('superseded_by_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_model_entries_workspace', 'model_entries', ['honcho_workspace_id'])
    op.create_table(
        'entity_links',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('object_type', sa.String(), nullable=False),
        sa.Column('object_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('entity_id', sa.Uuid(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('provenance_message_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_entity_links_object', 'entity_links', ['object_type', 'object_id'])
    op.create_index('ix_entity_links_entity', 'entity_links', ['entity_id'])
    op.create_table(
        'turn_frames',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('honcho_message_id', sa.String(), nullable=False),
        sa.Column('frame', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_turn_frames_message', 'turn_frames',
                    ['honcho_workspace_id', 'honcho_message_id'])

def downgrade():
    for table in ('turn_frames', 'entity_links', 'model_entries',
                  'relationship_edges', 'entity_aliases', 'entities'):
        op.drop_table(table)
