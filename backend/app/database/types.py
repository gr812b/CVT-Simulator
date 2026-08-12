"""Database column types used by the persistence layer.

The application tests run on SQLite, but production should use PostgreSQL.  Model
payloads are therefore declared with a portable type that maps to JSONB on
PostgreSQL and ordinary JSON on other dialects.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JsonPayload = JSON().with_variant(JSONB, "postgresql")
