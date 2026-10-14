import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.video import router as video_router
from app.db.session import SessionLocal
from app.models.analysis_job import AnalysisJob
from app.models.video import Video

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_orphaned_jobs()
    yield


app = FastAPI(
    title="Smartly AI API",
    version="0.1.0",
    description="AI-powered video analysis platform.",
    lifespan=lifespan,
)


def cleanup_orphaned_jobs() -> None:
    """
    Any job still marked 'running' when the server starts was
    interrupted by a restart/crash — its background thread is gone
    and it will never complete on its own. Mark these as 'failed'
    with an explicit reason instead of leaving them stuck forever
    in the UI, and mark their videos accordingly.
    """
    db = SessionLocal()
    try:
        orphaned_jobs = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.status == "running")
            .all()
        )

        for job in orphaned_jobs:
            job.status = "failed"
            job.current_stage = "error"
            job.error_message = (
                "Job interrupted by a server restart before completion. "
                "Please retry the analysis."
            )

            video = db.get(Video, job.video_id)
            if video is not None:
                video.status = "failed"

        if orphaned_jobs:
            db.commit()
            logger.warning(
                "Marked %d orphaned job(s) as failed on startup.",
                len(orphaned_jobs),
            )
    finally:
        db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router)
app.include_router(video_router)

# Sert le frontend React buildé (mode image unique en production).
# Monté uniquement si le dossier existe — le dev local (npm run dev
# sur un port séparé) n'est pas affecté.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")