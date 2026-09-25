"""Authoritative live scene state + epoch log (CurrentScene contract)."""
from alembic import op
import sqlalchemy as sa
revision = '0030_current_scene'
down_revision = '0029_claim_occurrence_identity'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'current_scenes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('epoch_id', sa.Integer(), nullable=False),
        sa.Column('fields_json', sa.String(), nullable=False),
        sa.Column('carried_matter_ids_json', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('honcho_workspace_id', 'honcho_session_id',
                            name='uq_current_scene_workspace_session'),
    )
    for col in ('honcho_workspace_id', 'honcho_session_id', 'epoch_id'):
        op.create_index(f'ix_current_scenes_{col}', 'current_scenes', [col])
    op.create_table(
        'scene_epochs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('honcho_workspace_id', sa.String(), nullable=False),
        sa.Column('honcho_session_id', sa.String(), nullable=False),
        sa.Column('epoch_id', sa.Integer(), nullable=False),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('close_reason', sa.String(), nullable=True),
        sa.Column('final_snapshot_json', sa.String(), nullable=False),
        sa.Column('carried_matter_ids_json', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('honcho_workspace_id', 'honcho_session_id', 'epoch_id'):
        op.create_index(f'ix_scene_epochs_{col}', 'scene_epochs', [col])

def downgrade():
    for col in ('epoch_id', 'honcho_session_id', 'honcho_workspace_id'):
        op.drop_index(f'ix_scene_epochs_{col}', table_name='scene_epochs')
    op.drop_table('scene_epochs')
    for col in ('epoch_id', 'honcho_session_id', 'honcho_workspace_id'):
        op.drop_index(f'ix_current_scenes_{col}', table_name='current_scenes')
    op.drop_table('current_scenes')
