from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    from app.models import log_source, settings as settings_model, summary, user

    del log_source, settings_model, summary, user
    if settings.database_url.startswith("sqlite:///"):
        database_path = settings.database_url.removeprefix("sqlite:///")
        if database_path != ":memory:":
            from pathlib import Path

            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as connection:
            columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(log_sources)")}
            if "source_type" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE log_sources ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'file'"
                )
            if "command" not in columns:
                connection.exec_driver_sql("ALTER TABLE log_sources ADD COLUMN command TEXT")
            summary_columns = {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(summaries)")
            }
            if "raw_input" not in summary_columns:
                connection.exec_driver_sql("ALTER TABLE summaries ADD COLUMN raw_input TEXT")
            if "raw_output" not in summary_columns:
                connection.exec_driver_sql("ALTER TABLE summaries ADD COLUMN raw_output TEXT")
            if "error_message" not in summary_columns:
                connection.exec_driver_sql("ALTER TABLE summaries ADD COLUMN error_message TEXT")
