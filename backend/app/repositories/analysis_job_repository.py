from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob


def create_analysis_job(
    db: Session,
    video_id: int,
) -> AnalysisJob:

    job = AnalysisJob(
        video_id=video_id,
        status="pending",
        current_stage="ingestion",
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


def get_latest_job_for_video(
    db: Session,
    video_id: int,
) -> AnalysisJob | None:

    return (
        db.query(AnalysisJob)
        .filter(AnalysisJob.video_id == video_id)
        .order_by(AnalysisJob.created_at.desc())
        .first()
    )