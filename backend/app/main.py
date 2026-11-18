from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import analyze_source, router, set_scheduler
from app.core.config import settings
from app.core.database import init_db
from app.services.scheduler import AnalysisScheduler

scheduler = AnalysisScheduler(analyze_source)
set_scheduler(scheduler)


@asynccontextmanager
async def lifespan(_: FastAPI):
    (settings.frontend_dir / "assets").mkdir(parents=True, exist_ok=True)
    init_db()
    scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.mount("/assets", StaticFiles(directory=settings.frontend_dir / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")
