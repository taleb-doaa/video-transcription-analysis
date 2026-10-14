import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.analysis_result import AnalysisResult
from app.models.video import Video
from app.models.transcript_segment import TranscriptSegment

from app.services.audio_service import extract_audio
from app.services.transcript_service import save_transcript_segments
from app.services.transcription_service import transcribe_audio
from app.services.diarization_service import diarize_audio
from app.services.alignment_service import merge_speakers
from app.services.analysis_service import analyze_transcript

logger = logging.getLogger(__name__)


def run_analysis_pipeline(
    db: Session,
    job_id: int,
) -> None:
    """
    Execute the complete video analysis pipeline.

    Pipeline:
        video
        -> audio extraction
        -> transcription
        -> speaker diarization
        -> transcript persistence
        -> AI analysis
        -> analysis result persistence
    """

    job = db.get(AnalysisJob, job_id)

    if job is None:
        raise ValueError(f"Analysis job {job_id} not found.")

    video = db.get(Video, job.video_id)

    if video is None:
        raise ValueError(f"Video {job.video_id} not found.")

    try:
        # ---------------------------------------------------------
        # 1. START JOB
        # ---------------------------------------------------------
        job.status = "running"
        job.current_stage = "audio_extraction"
        job.started_at = datetime.utcnow()
        job.error_message = None

        video.status = "processing"

        db.commit()

        # ---------------------------------------------------------
        # 2. AUDIO EXTRACTION
        # ---------------------------------------------------------
        if not video.file_path:
            raise ValueError(f"Video {video.id} does not have a file_path.")

        audio_path = f"/app/storage/audio/video_{video.id}.wav"

        extract_audio(video.file_path, audio_path)

        video.audio_path = audio_path

        db.commit()

        # ---------------------------------------------------------
        # 3 & 4. TRANSCRIPTION + SPEAKER DIARIZATION (parallel)
        # ---------------------------------------------------------
        # These two steps are independent (both only need audio_path),
        # so they run concurrently in separate threads to reduce total
        # processing time on CPU-only environments. Both faster-whisper
        # (ctranslate2) and pyannote (torch) release the GIL during
        # their heavy native computation, so ThreadPoolExecutor gives
        # real wall-clock speedup here, not just concurrency on paper.
        job.current_stage = "transcription"
        db.commit()

        with ThreadPoolExecutor(max_workers=2) as executor:
            transcription_future = executor.submit(transcribe_audio, audio_path)
            diarization_future = executor.submit(diarize_audio, audio_path)

            # Transcription failure is fatal to the pipeline (propagates).
            transcription = transcription_future.result()

            job.current_stage = "diarization"
            db.commit()

            number_of_speakers: int | None = None
            diarization_segments: list[dict] = []

            try:
                diarization_segments = diarization_future.result()
                number_of_speakers = len(
                    {seg["speaker"] for seg in diarization_segments}
                )
            except Exception as exc:
                # Diarization is not blocking: if it fails (missing
                # HF_TOKEN, model unavailable...), we keep the
                # transcript without speaker attribution instead of
                # failing the whole pipeline. We never guess the
                # number of speakers as a fallback.
                logger.warning("Diarization failed for video %s: %s", video.id, exc)
                job.error_message = f"Diarization skipped: {exc}"
                db.commit()

        segments_with_speakers = (
            merge_speakers(transcription["segments"], diarization_segments)
            if diarization_segments
            else transcription["segments"]
        )

        # ---------------------------------------------------------
        # 5. SAVE TRANSCRIPT
        # ---------------------------------------------------------
        job.current_stage = "saving_transcript"
        db.commit()

        save_transcript_segments(
            db=db,
            video_id=video.id,
            segments=segments_with_speakers,
        )

        # ---------------------------------------------------------
        # 6. AI ANALYSIS
        # ---------------------------------------------------------
        job.current_stage = "ai_analysis"
        db.commit()

        transcript_rows = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.video_id == video.id)
            .order_by(TranscriptSegment.start)
            .all()
        )

        if not transcript_rows:
            raise ValueError(f"No transcript segments found for video {video.id}.")

        segments = [
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text,
            }
            for segment in transcript_rows
        ]

        analysis = analyze_transcript(segments)

        # Trust the diarization count over the LLM's guess.
        analysis["number_of_speakers"] = (
            number_of_speakers
            if number_of_speakers is not None
            else analysis.get("number_of_speakers")
        )

        # ---------------------------------------------------------
        # 7. SAVE ANALYSIS RESULT
        # ---------------------------------------------------------
        job.current_stage = "saving_analysis"
        db.commit()

        existing_result = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.video_id == video.id)
            .first()
        )

        if existing_result:
            existing_result.number_of_speakers = analysis["number_of_speakers"]
            existing_result.summary = analysis["summary"]
            existing_result.key_points = analysis["key_points"]
            existing_result.topics = analysis["topics"]
        else:
            analysis_result = AnalysisResult(
                video_id=video.id,
                number_of_speakers=analysis["number_of_speakers"],
                summary=analysis["summary"],
                key_points=analysis["key_points"],
                topics=analysis["topics"],
            )
            db.add(analysis_result)

        db.commit()

        # ---------------------------------------------------------
        # 8. COMPLETE
        # ---------------------------------------------------------
        job.current_stage = "completed"
        job.status = "completed"
        job.completed_at = datetime.utcnow()

        video.status = "completed"

        db.commit()

    except Exception as exc:
        logger.exception("Analysis pipeline failed for job %s", job_id)

        db.rollback()

        job = db.get(AnalysisJob, job_id)

        if job is not None:
            job.status = "failed"
            job.current_stage = "error"
            job.error_message = str(exc)

        video = db.get(Video, job.video_id) if job else None

        if video is not None:
            video.status = "failed"

        db.commit()

        raise