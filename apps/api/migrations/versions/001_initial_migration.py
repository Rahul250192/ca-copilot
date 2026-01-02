"""initial_migration

Revision ID: 001
Revises: 
Create Date: 2025-12-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create Firms table
    op.create_table('firms',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create Users table
    op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('role', sa.Enum('OWNER', 'ADMIN', 'STAFF', name='userrole'), nullable=True),
        sa.Column('firm_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['firm_id'], ['firms.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # Create Clients table
    op.create_table('clients',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('firm_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['firm_id'], ['firms.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create Kits table
    op.create_table('kits',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create Conversations table
    op.create_table('conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('firm_id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['firm_id'], ['firms.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Association table: conversation_kits
    op.create_table('conversation_kits',
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('kit_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.ForeignKeyConstraint(['kit_id'], ['kits.id'], ),
        sa.PrimaryKeyConstraint('conversation_id', 'kit_id')
    )

    # Create Messages table
    op.create_table('messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.Enum('USER', 'ASSISTANT', 'SYSTEM', name='messagerole'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create Documents table
    op.create_table('documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('scope', sa.Enum('FIRM', 'KIT', 'CLIENT', name='scope'), nullable=False),
        sa.Column('firm_id', sa.UUID(), nullable=True),
        sa.Column('client_id', sa.UUID(), nullable=True),
        sa.Column('kit_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.Enum('UPLOADED', 'PROCESSING', 'READY', 'FAILED', name='documentstatus'), nullable=True),
        sa.Column('file_path', sa.String(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("(scope = 'FIRM' AND kit_id IS NULL AND client_id IS NULL) OR (scope = 'KIT' AND kit_id IS NOT NULL AND client_id IS NULL) OR (scope = 'CLIENT' AND client_id IS NOT NULL AND kit_id IS NULL)", name='check_scope_constraints'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.ForeignKeyConstraint(['firm_id'], ['firms.id'], ),
        sa.ForeignKeyConstraint(['kit_id'], ['kits.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create DocEmbeddings table
    op.create_table('doc_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Add HNSW index for vector search
    # m=16, ef_construction=64 are reasonable defaults
    op.execute('CREATE INDEX ON doc_embeddings USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64)')


    # Create RetrievalLogs table
    op.create_table('retrieval_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('cited_chunks', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('retrieval_logs')
    op.drop_table('doc_embeddings')
    op.drop_table('documents')
    op.drop_table('messages')
    op.drop_table('conversation_kits')
    op.drop_table('conversations')
    op.drop_table('kits')
    op.drop_table('clients')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('firms')
    op.execute('DROP EXTENSION IF EXISTS vector')
