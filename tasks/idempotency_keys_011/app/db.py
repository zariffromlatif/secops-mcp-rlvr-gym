import os

from sqlalchemy import create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://gym:gym@localhost:5433/gym")

engine = create_engine(DATABASE_URL)


def get_db():
    with engine.connect() as conn:
        yield conn
