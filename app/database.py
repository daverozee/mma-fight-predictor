from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

if database_url.startswith("sqlite:///"):
    db_path = database_url.replace("sqlite:///", "", 1)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()


def ensure_runtime_schema() -> None:
    with engine.begin() as connection:
        if database_url.startswith("sqlite"):
            ensure_sqlite_schema(connection)
        elif connection.dialect.name == "postgresql":
            ensure_postgres_schema(connection)


def ensure_sqlite_schema(connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute(text("PRAGMA table_info(fighter_profiles)")).mappings()
    }
    if "instagram_url" not in columns:
        connection.execute(text("ALTER TABLE fighter_profiles ADD COLUMN instagram_url TEXT"))
    fight_columns = {
        row["name"]
        for row in connection.execute(text("PRAGMA table_info(fight_results)")).mappings()
    }
    for column_name, column_type in fight_result_runtime_columns().items():
        if column_name not in fight_columns:
            connection.execute(
                text(f"ALTER TABLE fight_results ADD COLUMN {column_name} {column_type}")
            )


def ensure_postgres_schema(connection) -> None:
    connection.execute(text("ALTER TABLE fighter_profiles ADD COLUMN IF NOT EXISTS instagram_url TEXT"))
    for column_name, column_type in fight_result_runtime_columns(postgres=True).items():
        connection.execute(
            text(f"ALTER TABLE fight_results ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
        )


def fight_result_runtime_columns(postgres: bool = False) -> dict[str, str]:
    integer_type = "INTEGER"
    return {
        "promotion": "VARCHAR(120)" if postgres else "TEXT",
        "weight_class": "VARCHAR(80)" if postgres else "TEXT",
        "scheduled_rounds": integer_type,
        "finish_round": integer_type,
        "finish_time": "VARCHAR(20)" if postgres else "TEXT",
    }
