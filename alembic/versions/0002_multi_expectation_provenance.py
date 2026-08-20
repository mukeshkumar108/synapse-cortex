"""support multiple expectation candidates per message

Revision ID: 0002_multi_expectation
Revises: 0001_initial
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_multi_expectation"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Kept as an explicit revision boundary. The pre-production 0001 schema was
    # consolidated before deployment and already contains these columns/constraint.
    pass


def downgrade() -> None:
    pass
