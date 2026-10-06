"""Add credentials and revocable sessions without assigning passwords to legacy users."""

import sqlalchemy as sa
from alembic import op

revision = "20261003_0005"
down_revision = "20260916_0004"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    duplicates = connection.execute(
        sa.text(
            "SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Resolve users with case-insensitive duplicate emails before migrating."
        )
    # The historical 0001 migration creates live ORM metadata on a fresh DB.
    # Real upgrades still need these additions; fresh installs already have them.
    columns = {column["name"] for column in sa.inspect(connection).get_columns("users")}
    if "password_hash" not in columns:
        op.add_column(
            "users", sa.Column("password_hash", sa.String(500), nullable=True)
        )
    if "auth_version" not in columns:
        op.add_column(
            "users",
            sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False),
        )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_normalized ON users (lower(email))"
        )
    )
    _create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    _create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    _create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    _create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
    )
    _create_index(
        "ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"]
    )
    _create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    _create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])


def downgrade():
    op.drop_table("auth_rate_limits")
    op.drop_table("password_reset_tokens")
    op.drop_table("auth_sessions")
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "password_hash")


def _create_table(name, *columns):
    if name not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(name, *columns)


def _create_index(name, table, columns):
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)
