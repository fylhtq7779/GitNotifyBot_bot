from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models so Base.metadata is populated for Alembic and tests.
from app.storage import models  # noqa: E402,F401
