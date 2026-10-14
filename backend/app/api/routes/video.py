import os
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from sqlalchemy import func

from app.db.session import SessionLocal, get_db
from app.models.video import Video
from app.models.transcript_segment import TranscriptSegment
from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.repositories.analysis_job_repository import (
    create_analysis_job,
    get_latest_job_for_video,
)
from app.repositories.analysis_result_repository import get_analysis_result
from app.repositories.video_repository import create_video
from app.schemas.analysis import AnalysisResultResponse
from app.schemas.job import AnalyzeVideoResponse, JobStatusResponse
from app.schemas.video import VideoResponse, VideoURLRequest
from app.services.analysis_pipeline import run_analysis_pipeline
from app.services.storage_service import generate_video_path
from app.services.video_service import VideoIngestionError, download_video
from app.services.media_utils import get_video_duration
from app.services.srt_service import generate_srt

import logging


router = APIRouter(
    prefix="/videos",
    tags=["Videos"],
)


logger = logging.getLogger(__name__)

def _run_analysis_background(job_id: int) -> None:
    """
    Execute the analysis pipeline in a dedicated database session.

    Any exception is caught and logged here: the pipeline already
    persists the failure in AnalysisJob/Video, so re-raising would
    only crash the ASGI application since this runs outside the
    request/response cycle.
    """
    db = SessionLocal()

    try:
        run_analysis_pipeline(db=db, job_id=job_id)
    except Exception:
        logger.exception(
            "Analysis pipeline crashed for job %s", job_id
        )
    finally:
        db.close()

@router.get("/")
def list_videos(db: Session = Depends(get_db)):
    """
    Return all videos with their latest job status, most recent first —
    used by the frontend History page.
    """

    videos = (
        db.query(Video)
        .order_by(Video.id.desc())
        .all()
    )

    results = []

    for video in videos:
        job = get_latest_job_for_video(db, video.id)

        results.append({
            "id": video.id,
            "title": video.title,
            "description": video.description,
            "source_type": video.source_type,
            "source_url": video.source_url,
            "duration": video.duration,
            "status": job.status if job else "unknown",
            "created_at": job.created_at if job else None,
        })

    return results

@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Aggregate stats for the frontend Dashboard: counts by status,
    average processing time, total duration processed, average
    number of speakers detected, and the 5 most recent analyses.
    """

    status_rows = (
        db.query(Video.status, func.count(Video.id))
        .group_by(Video.status)
        .all()
    )
    status_counts = {status: count for status, count in status_rows}

    total_videos = sum(status_counts.values())
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    processing = status_counts.get("processing", 0) + status_counts.get("pending", 0)

    completed_jobs = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.status == "completed",
            AnalysisJob.started_at.isnot(None),
            AnalysisJob.completed_at.isnot(None),
        )
        .all()
    )

    avg_processing_seconds = None
    if completed_jobs:
        total_seconds = sum(
            (job.completed_at - job.started_at).total_seconds()
            for job in completed_jobs
        )
        avg_processing_seconds = round(total_seconds / len(completed_jobs), 1)

    total_duration_seconds = (
        db.query(func.coalesce(func.sum(Video.duration), 0.0))
        .filter(Video.status == "completed")
        .scalar()
    )

    avg_speakers = (
        db.query(func.avg(AnalysisResult.number_of_speakers))
        .filter(AnalysisResult.number_of_speakers.isnot(None))
        .scalar()
    )

    recent_videos = (
        db.query(Video)
        .order_by(Video.id.desc())
        .limit(5)
        .all()
    )

    return {
        "total_videos": total_videos,
        "completed": completed,
        "failed": failed,
        "processing": processing,
        "avg_processing_seconds": avg_processing_seconds,
        "total_duration_seconds": round(float(total_duration_seconds or 0), 1),
        "avg_speakers": round(float(avg_speakers), 1) if avg_speakers is not None else None,
        "recent": [
            {
                "id": v.id,
                "title": v.title,
                "status": v.status,
                "source_type": v.source_type,
                "duration": v.duration,
                "created_at": v.created_at,
            }
            for v in recent_videos
        ],
    }

@router.post(
    "/analyze-video",
    response_model=AnalyzeVideoResponse,
)
def analyze_video_from_url(
    request: VideoURLRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Download a video from a URL, create its analysis job and start
    the analysis pipeline in the background.
    """

    try:
        data = download_video(request.url)

        video = create_video(
            db,
            source_type=data["source_type"],
            source_url=data["source_url"],
            title=data["title"],
            description=data["description"],
            duration=data["duration"],
            file_path=data["file_path"],
        )

        job = create_analysis_job(db, video.id)

        background_tasks.add_task(_run_analysis_background, job.id)

        return AnalyzeVideoResponse(
            video=VideoResponse.model_validate(video),
            job_id=job.id,
        )

    except VideoIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/analyze-video/upload",
    response_model=AnalyzeVideoResponse,
)
async def analyze_video_from_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a local video file, create its analysis job and start
    the analysis pipeline in the background.
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    extension = Path(file.filename).suffix or ".mp4"
    output_path = generate_video_path(extension)

    try:
        with open(output_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {exc}",
        ) from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty or could not be saved.",
        )

    duration = get_video_duration(str(output_path))

    video = create_video(
        db,
        source_type="upload",
        source_url=None,
        title=file.filename,
        description=None,
        duration=duration,
        file_path=str(output_path),
    )

    job = create_analysis_job(db, video.id)

    background_tasks.add_task(_run_analysis_background, job.id)

    return AnalyzeVideoResponse(
        video=VideoResponse.model_validate(video),
        job_id=job.id,
    )


@router.get(
    "/{video_id}/status",
    response_model=JobStatusResponse,
)
def get_video_status(
    video_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the latest analysis job status for a video, so the
    frontend can poll it and show real-time progress.
    """

    job = get_latest_job_for_video(db, video_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="No analysis job found for this video.",
        )

    return job


@router.get(
    "/{video_id}/analysis",
    response_model=AnalysisResultResponse,
)
def get_video_analysis(
    video_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the raw AI analysis result row for a video.
    """

    result = get_analysis_result(db, video_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis result not found for this video.",
        )

    return result


@router.get("/{video_id}/result")
def get_full_result(
    video_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the full result matching the challenge's expected output
    format: metadata + full timestamped/speaker-labeled transcript
    + LLM analysis.
    """

    video = db.get(Video, video_id)

    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    result = get_analysis_result(db, video_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not available yet for this video.",
        )

    transcript_rows = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.start)
        .all()
    )

    return {
        "title": video.title,
        "duration": video.duration,
        "number_of_speakers": result.number_of_speakers,
        "transcript": [
            {
                "start": seg.start,
                "end": seg.end,
                "speaker": seg.speaker,
                "text": seg.text,
            }
            for seg in transcript_rows
        ],
        "summary": result.summary,
        "key_points": result.key_points,
        "topics": result.topics,
    }


@router.get("/{video_id}/subtitles.srt")
def get_subtitles(
    video_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the transcript as a downloadable .srt subtitle file,
    compatible with VLC, YouTube, and other standard video players.
    """

    video = db.get(Video, video_id)

    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    transcript_rows = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.video_id == video_id)
        .order_by(TranscriptSegment.start)
        .all()
    )

    if not transcript_rows:
        raise HTTPException(
            status_code=404,
            detail="No transcript available yet for this video.",
        )

    segments = [
        {
            "start": seg.start,
            "end": seg.end,
            "speaker": seg.speaker,
            "text": seg.text,
        }
        for seg in transcript_rows
    ]

    try:
        srt_content = generate_srt(segments)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = f"{(video.title or f'video_{video.id}').rsplit('.', 1)[0]}.srt"

    return Response(
        content=srt_content,
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{video_id}/retry",
    response_model=AnalyzeVideoResponse,
)
def retry_video_analysis(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Retry a failed analysis without re-downloading or re-uploading
    the video: reuses the existing file_path and starts a fresh
    AnalysisJob for it.
    """

    video = db.get(Video, video_id)

    if video is None:
        raise HTTPException(status_code=404, detail="Video not found.")

    latest_job = get_latest_job_for_video(db, video_id)

    if latest_job is None:
        raise HTTPException(
            status_code=404,
            detail="No analysis job found for this video.",
        )

    if latest_job.status not in ("failed", "completed"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot retry: current job status is '{latest_job.status}'. "
                "Only failed or completed analyses can be retried."
            ),
        )

    if not video.file_path or not os.path.exists(video.file_path):
        raise HTTPException(
            status_code=400,
            detail=(
                "Original video file is no longer available on disk. "
                "Please re-submit the video (URL or upload) instead."
            ),
        )

    video.status = "pending"
    db.commit()

    job = create_analysis_job(db, video.id)

    background_tasks.add_task(_run_analysis_background, job.id)

    return AnalyzeVideoResponse(
        video=VideoResponse.model_validate(video),
        job_id=job.id,
    )