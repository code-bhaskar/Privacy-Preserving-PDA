"""initial_schema

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # consents
    op.create_table(
        'consents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'category', name='uq_user_category')
    )
    op.create_index(op.f('ix_consents_user_id'), 'consents', ['user_id'], unique=False)

    # calendar_events
    op.create_table(
        'calendar_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('participant', sa.String(length=120), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_via', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_calendar_events_user_id'), 'calendar_events', ['user_id'], unique=False)

    # reminders
    op.create_table(
        'reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(length=500), nullable=False),
        sa.Column('due_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reminders_user_id'), 'reminders', ['user_id'], unique=False)

    # messages
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content_encrypted', sa.Text(), nullable=False),
        sa.Column('sender', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_user_id'), 'messages', ['user_id'], unique=False)

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=80), nullable=False),
        sa.Column('data_type', sa.String(length=60), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('external_processing', sa.Boolean(), nullable=False),
        sa.Column('processing_location', sa.String(length=20), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=True),
        sa.Column('integrity_hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)

    # model_updates
    op.create_table(
        'model_updates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('round_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.String(length=40), nullable=False),
        sa.Column('dp_epsilon', sa.Float(), nullable=True),
        sa.Column('dp_delta', sa.Float(), nullable=True),
        sa.Column('clip_norm', sa.Float(), nullable=False),
        sa.Column('payload_bytes', sa.Integer(), nullable=False),
        sa.Column('masked', sa.Boolean(), nullable=False),
        sa.Column('n_local_samples', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_updates_round_id'), 'model_updates', ['round_id'], unique=False)

    # federated_rounds
    op.create_table(
        'federated_rounds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('round_id', sa.Integer(), nullable=False),
        sa.Column('n_clients', sa.Integer(), nullable=False),
        sa.Column('dp_epsilon', sa.Float(), nullable=True),
        sa.Column('global_accuracy', sa.Float(), nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=False),
        sa.Column('comm_bytes_total', sa.Integer(), nullable=False),
        sa.Column('model_size_bytes', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_federated_rounds_round_id'), 'federated_rounds', ['round_id'], unique=False)


def downgrade() -> None:
    op.drop_table('federated_rounds')
    op.drop_table('model_updates')
    op.drop_table('audit_logs')
    op.drop_table('messages')
    op.drop_table('reminders')
    op.drop_table('calendar_events')
    op.drop_table('consents')
    op.drop_table('users')
