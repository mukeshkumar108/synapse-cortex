"""Fix claim identity: occurrence key replaces content-hash identity.

0028 keyed claims by (workspace, content_hash), which collapses semantically
distinct occurrences of identical wording (Ashley Monday vs Sophie three
weeks later saying "I'll call you tomorrow"). Identity is now
(workspace, content_hash, source_key); cross-occurrence sameness is a
same_as relation, never a merge.
"""
from alembic import op
import sqlalchemy as sa
revision = '0029_claim_occurrence_identity'
down_revision = '0028_semantic_relations'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('semantic_claims',
                  sa.Column('source_key', sa.String(), nullable=False,
                            server_default='legacy-occurrence'))
    op.drop_constraint('uq_semantic_claim_workspace_hash', 'semantic_claims',
                       type_='unique')
    op.create_unique_constraint('uq_semantic_claim_occurrence', 'semantic_claims',
                                ['honcho_workspace_id', 'content_hash', 'source_key'])
    op.create_index('ix_semantic_claims_source_key', 'semantic_claims', ['source_key'])
    # Logical edge identity lives on content hashes so corroborating evidence
    # grows one row; endpoints still reference occurrence claim rows. Subject
    # keys keep identical wording with disjoint known subjects apart.
    op.add_column('semantic_relations',
                  sa.Column('from_content_hash', sa.String(), nullable=False,
                            server_default='legacy'))
    op.add_column('semantic_relations',
                  sa.Column('to_content_hash', sa.String(), nullable=False,
                            server_default='legacy'))
    op.add_column('semantic_relations',
                  sa.Column('from_subj_key', sa.String(), nullable=False,
                            server_default=''))
    op.add_column('semantic_relations',
                  sa.Column('to_subj_key', sa.String(), nullable=False,
                            server_default=''))
    op.create_index('ix_semantic_relations_from_content_hash', 'semantic_relations',
                    ['from_content_hash'])
    op.create_index('ix_semantic_relations_to_content_hash', 'semantic_relations',
                    ['to_content_hash'])
    op.create_index(
        'uq_semantic_relation_logical_edge', 'semantic_relations',
        ['honcho_workspace_id', 'from_content_hash', 'to_content_hash', 'rel_type',
         'from_subj_key', 'to_subj_key'],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

def downgrade():
    op.drop_index('uq_semantic_relation_logical_edge', table_name='semantic_relations')
    op.drop_index('ix_semantic_relations_to_content_hash', table_name='semantic_relations')
    op.drop_index('ix_semantic_relations_from_content_hash', table_name='semantic_relations')
    op.drop_column('semantic_relations', 'to_subj_key')
    op.drop_column('semantic_relations', 'from_subj_key')
    op.drop_column('semantic_relations', 'to_content_hash')
    op.drop_column('semantic_relations', 'from_content_hash')
    op.drop_index('ix_semantic_claims_source_key', table_name='semantic_claims')
    op.drop_constraint('uq_semantic_claim_occurrence', 'semantic_claims',
                       type_='unique')
    op.create_unique_constraint('uq_semantic_claim_workspace_hash', 'semantic_claims',
                                ['honcho_workspace_id', 'content_hash'])
    op.drop_column('semantic_claims', 'source_key')
