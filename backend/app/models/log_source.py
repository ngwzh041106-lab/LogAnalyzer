from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LogSource(Base):
    __tablename__ = "log_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(16), default="file")
    path: Mapped[str] = mapped_column(String(1024), default="")
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    read_mode: Mapped[str] = mapped_column(String(32), default="tail_lines")
    tail_lines: Mapped[int] = mapped_column(Integer, default=500)
    tail_bytes: Mapped[int] = mapped_column(Integer, default=262144)
    include_patterns: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclude_patterns: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_minutes: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
