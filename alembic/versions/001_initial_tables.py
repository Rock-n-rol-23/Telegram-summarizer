"""Initial database tables

Revision ID: 001
Revises: 
Create Date: 2025-08-22 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User requests table
    op.create_table(
        'user_requests',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.BigInteger, nullable=False),
        sa.Column('request_type', sa.String(50), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('processing_time', sa.Float, nullable=True),
        sa.Column('compression_ratio', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    op.create_index('idx_user_requests_user_id', 'user_requests', ['user_id'])
    op.create_index('idx_user_requests_created_at', 'user_requests', ['created_at'])
    
    # User settings table
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.BigInteger, primary_key=True),
        sa.Column('audio_format', sa.String(20), default='structured'),
        sa.Column('audio_verbosity', sa.String(20), default='normal'),
        sa.Column('preferred_compression', sa.Float, default=0.3),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    # Web cache table
    op.create_table(
        'web_cache',
        sa.Column('url_hash', sa.String(64), primary_key=True),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('content', sa.Text, nullable=True),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('cached_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    op.create_index('idx_web_cache_cached_at', 'web_cache', ['cached_at'])


def downgrade() -> None:
    op.drop_table('web_cache')
    op.drop_table('user_settings') 
    op.drop_table('user_requests')