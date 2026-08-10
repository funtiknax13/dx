"""Cities table (GeoNames) + users.city_id

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_ascii", sa.String(length=200), nullable=False),
        sa.Column("search_name", sa.String(length=200), nullable=False),
        sa.Column("search_ascii", sa.String(length=200), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=160), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("city_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_city_id", "users", ["city_id"])
    op.create_foreign_key(
        "fk_users_city_id_cities",
        "users",
        "cities",
        ["city_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Postgres-only: trigram indexes for fast fuzzy/prefix search on both the
    # Russian and Latin names. Skipped on SQLite (tests), which has no pg_trgm.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX ix_cities_search_name_trgm ON cities "
            "USING gin (search_name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX ix_cities_search_ascii_trgm ON cities "
            "USING gin (search_ascii gin_trgm_ops)"
        )
        op.execute("CREATE INDEX ix_cities_population ON cities (population DESC)")
    else:
        op.create_index("ix_cities_search_name", "cities", ["search_name"])
        op.create_index("ix_cities_search_ascii", "cities", ["search_ascii"])


def downgrade() -> None:
    op.drop_constraint("fk_users_city_id_cities", "users", type_="foreignkey")
    op.drop_index("ix_users_city_id", table_name="users")
    op.drop_column("users", "city_id")
    op.drop_table("cities")
