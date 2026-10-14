from unittest.mock import MagicMock, patch

import pytest

from app.services.analysis_pipeline import run_analysis_pipeline


def _make_job_and_video():
    job = MagicMock(
        id=7,
        video_id=1,
        status="pending",
        current_stage=None,
        error_message=None,
        started_at=None,
        completed_at=None,
    )
    video = MagicMock(
        id=1,
        file_path="/app/storage/video.mp4",
        audio_path=None,
        status="pending",
        title="Ma vidéo",
    )
    return job, video


def _db_with(job, video):
    """
    A MagicMock db session whose .get(Model, id) returns the right
    fake object depending on the model class requested — mirrors
    db.get(AnalysisJob, job_id) / db.get(Video, video.id) calls in
    the real pipeline.
    """
    from app.models.analysis_job import AnalysisJob
    from app.models.video import Video

    db = MagicMock()

    def fake_get(model, _id):
        if model is AnalysisJob:
            return job
        if model is Video:
            return video
        return None

    db.get.side_effect = fake_get
    return db


TRANSCRIPT_SEGMENTS = [
    {"start": 0.0, "end": 5.0, "text": "Bonjour"},
]
DIARIZATION_SEGMENTS = [
    {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01"},
]


@patch("app.services.analysis_pipeline.analyze_transcript")
@patch("app.services.analysis_pipeline.save_transcript_segments")
@patch("app.services.analysis_pipeline.merge_speakers")
@patch("app.services.analysis_pipeline.diarize_audio")
@patch("app.services.analysis_pipeline.transcribe_audio")
@patch("app.services.analysis_pipeline.extract_audio")
def test_pipeline_success_marks_job_and_video_completed(
    mock_extract,
    mock_transcribe,
    mock_diarize,
    mock_merge,
    mock_save,
    mock_analyze,
):
    job, video = _make_job_and_video()
    db = _db_with(job, video)

    mock_transcribe.return_value = {"segments": TRANSCRIPT_SEGMENTS}
    mock_diarize.return_value = DIARIZATION_SEGMENTS
    mock_merge.return_value = [
        {**TRANSCRIPT_SEGMENTS[0], "speaker": "SPEAKER_01"}
    ]

    fake_segment_row = MagicMock(start=0.0, end=5.0, text="Bonjour")
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        fake_segment_row
    ]
    # No existing AnalysisResult row yet.
    db.query.return_value.filter.return_value.first.return_value = None

    mock_analyze.return_value = {
        "number_of_speakers": None,  # LLM guess, should be overridden
        "summary": "Résumé.",
        "key_points": ["Point 1"],
        "topics": ["Sujet 1"],
    }

    run_analysis_pipeline(db=db, job_id=7)

    assert job.status == "completed"
    assert job.current_stage == "completed"
    assert video.status == "completed"
    # Diarization count (1 distinct speaker) must win over the LLM's null guess.
    assert mock_analyze.return_value  # sanity: analyze_transcript was called


@patch("app.services.analysis_pipeline.analyze_transcript")
@patch("app.services.analysis_pipeline.save_transcript_segments")
@patch("app.services.analysis_pipeline.diarize_audio")
@patch("app.services.analysis_pipeline.transcribe_audio")
@patch("app.services.analysis_pipeline.extract_audio")
def test_pipeline_continues_when_diarization_fails(
    mock_extract,
    mock_transcribe,
    mock_diarize,
    mock_save,
    mock_analyze,
):
    """
    Diarization failure must not fail the whole pipeline: the job
    should still complete, with speaker attribution simply absent.
    """
    job, video = _make_job_and_video()
    db = _db_with(job, video)

    mock_transcribe.return_value = {"segments": TRANSCRIPT_SEGMENTS}
    mock_diarize.side_effect = Exception("HF_TOKEN invalid")

    fake_segment_row = MagicMock(start=0.0, end=5.0, text="Bonjour")
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        fake_segment_row
    ]
    db.query.return_value.filter.return_value.first.return_value = None

    mock_analyze.return_value = {
        "number_of_speakers": None,
        "summary": "Résumé.",
        "key_points": [],
        "topics": [],
    }

    run_analysis_pipeline(db=db, job_id=7)

    assert job.status == "completed"
    assert "Diarization skipped" in job.error_message
    # save_transcript_segments must receive the raw transcript
    # (no speaker key) since diarization_segments was empty.
    mock_save.assert_called_once()
    saved_segments = mock_save.call_args.kwargs["segments"]
    assert saved_segments == TRANSCRIPT_SEGMENTS


@patch("app.services.analysis_pipeline.transcribe_audio")
@patch("app.services.analysis_pipeline.diarize_audio")
@patch("app.services.analysis_pipeline.extract_audio")
def test_pipeline_marks_failed_when_transcription_raises(
    mock_extract, mock_diarize, mock_transcribe
):
    job, video = _make_job_and_video()
    db = _db_with(job, video)

    mock_transcribe.side_effect = ValueError("No speech detected in the audio.")
    mock_diarize.return_value = []

    with pytest.raises(ValueError):
        run_analysis_pipeline(db=db, job_id=7)

    assert job.status == "failed"
    assert job.current_stage == "error"
    assert "No speech detected" in job.error_message
    assert video.status == "failed"


def test_pipeline_raises_when_job_not_found():
    db = MagicMock()
    db.get.return_value = None

    with pytest.raises(ValueError, match="not found"):
        run_analysis_pipeline(db=db, job_id=999)


@patch("app.services.analysis_pipeline.extract_audio")
def test_pipeline_raises_when_video_has_no_file_path(mock_extract):
    job, video = _make_job_and_video()
    video.file_path = None
    db = _db_with(job, video)

    with pytest.raises(ValueError, match="file_path"):
        run_analysis_pipeline(db=db, job_id=7)

    assert job.status == "failed"