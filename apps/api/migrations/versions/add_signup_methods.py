"""add signup method and auth flexibility

Revision ID: add_signup_methods
Revises: c9f66007637c
Create Date: 2026-03-07 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_signup_methods'
down_revision: Union[str, None] = 'c9f66007637c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]

    # 1. Create the signup_method enum type
    signup_method_enum = sa.Enum('email', 'phone', 'google', name='signupmethod')
    signup_method_enum.create(conn, checkfirst=True)

    # 2. Add signup_method column (default='email' for existing users)
    if 'signup_method' not in columns:
        op.add_column('users', sa.Column(
            'signup_method',
            sa.Enum('email', 'phone', 'google', name='signupmethod'),
            nullable=False,
            server_default='email',
        ))

    # 3. Make email nullable (for phone-only signups)
    op.alter_column('users', 'email', existing_type=sa.String(), nullable=True)

    # 4. Make hashed_password nullable (for Google OAuth signups)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(), nullable=True)

    # 5. Make phone_number unique and indexed (for phone-based login)
    #    First check if index/constraint exists
    indexes = [idx['name'] for idx in inspector.get_indexes('users')]
    unique_constraints = [uc['name'] for uc in inspector.get_unique_constraints('users')]

    if 'ix_users_phone_number' not in indexes:
        op.create_index('ix_users_phone_number', 'users', ['phone_number'], unique=True)


def downgrade() -> None:
    # Remove unique index on phone_number
    op.drop_index('ix_users_phone_number', table_name='users')

    # Revert email to non-nullable
    op.alter_column('users', 'email', existing_type=sa.String(), nullable=False)

    # Revert hashed_password to non-nullable
    op.alter_column('users', 'hashed_password', existing_type=sa.String(), nullable=False)

    # Drop signup_method column
    op.drop_column('users', 'signup_method')

    # Drop enum type
    sa.Enum(name='signupmethod').drop(op.get_bind(), checkfirst=True)
