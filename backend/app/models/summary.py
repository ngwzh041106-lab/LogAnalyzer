from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_source_id: Mapped[int | None] = mapped_column(ForeignKey("log_sources.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="placeholder")
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
