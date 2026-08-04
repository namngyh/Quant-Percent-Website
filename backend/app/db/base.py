from datetime import datetime

from sqlalchemy import MetaData, text
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import DateTime

# Predictable constraint names keep Alembic autogenerate stable
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Schemas owned by this service
WEB_SCHEMA = "web"
# Written by the model pipeline, read-only here
QUANT_SCHEMA = "quant"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow_column(**kwargs: object):
    """timestamptz column defaulting to the database clock."""
    return mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
        **kwargs,  # type: ignore[arg-type]
    )


__all__ = ["Base", "WEB_SCHEMA", "QUANT_SCHEMA", "utcnow_column", "datetime"]
