import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.models.log_source import LogSource
from app.services.llm_client import LLMError
from app.services.log_reader import LogReadError

logger = logging.getLogger(__name__)


class AnalysisScheduler:
    def __init__(self, analyze_source):
        self.analyze_source = analyze_source
        self.task: asyncio.Task | None = None
        self.next_runs: dict[int, datetime] = {}

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run(), name="log-analysis-scheduler")
            logger.info("Log analysis scheduler started")

    @property
    def status(self) -> str:
        if self.task is None:
            return "stopped"
        if self.task.cancelled():
            return "stopped"
        if self.task.done():
            return "failed"
        return "running"

    async def stop(self) -> None:
        if self.task is None:
            return
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        logger.info("Log analysis scheduler stopped")

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                try:
                    await asyncio.to_thread(self._run_due_sources)
                except Exception:
                    logger.exception("Unexpected error in scheduled analysis cycle")
        except asyncio.CancelledError:
            raise

    def _run_due_sources(self) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            with SessionLocal() as db:
                sources = list(
                    db.query(LogSource)
                    .filter(LogSource.enabled.is_(True))
                    .order_by(LogSource.id)
                    .all()
                )

                active_ids = {source.id for source in sources}
                self.next_runs = {
                    source_id: run_at
                    for source_id, run_at in self.next_runs.items()
                    if source_id in active_ids
                }

                for source in sources:
                    next_run = self.next_runs.get(source.id)
                    if next_run is None:
                        self.next_runs[source.id] = now + timedelta(
                            minutes=max(1, source.schedule_minutes)
                        )
                        continue
                    if now < next_run:
                        continue

                    try:
                        self.analyze_source(db, source)
                    except (LogReadError, LLMError, SQLAlchemyError):
                        db.rollback()
                        logger.exception(
                            "Scheduled analysis failed for log source id=%s name=%s",
                            source.id,
                            source.name,
                        )
                    finally:
                        self.next_runs[source.id] = now + timedelta(
                            minutes=max(1, source.schedule_minutes)
                        )
        except SQLAlchemyError:
            logger.exception("Unable to load log sources for scheduled analysis")
