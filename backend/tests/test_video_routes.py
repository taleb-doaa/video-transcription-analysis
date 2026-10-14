from unittest.mock import MagicMock, patch

import pytest

from app.services.video_service import VideoIngestionError


@pytest.fixture(autouse=True)
def mock_background_pipeline():
    """
    Route tests only check the HTTP contract (status codes, response
    shape) of the /analyze-video endpoints, not the pipeline itself
    (already covered by test_analysis_pipeline.py). Without this,
    FastAPI's BackgroundTasks actually run after the response in
    TestClient, triggering real Whisper/pyannote model loading and
    hanging the test suite for minutes.
    """
    with patch("app.api.routes.video._run_analysis_background") as mock_task:
        yield mock_task


# ---------------------------------------------------------------
# POST /videos/analyze-video
# ---------------------------------------------------------------

@patch("app.api.routes.video.create_analysis_job")
@patch("app.api.routes.video.create_video")
@patch("app.api.routes.video.download_video")
def test_analyze_video_from_url_success(
    mock_download, mock_create_video, mock_create_job, client
):
    mock_download.return_value = {
        "source_type": "url",
        "source_url": "https://example.com/video",
        "title": "Ma vidéo",
        "description": None,
        "duration": 120.0,
        "file_path": "/app/storage/video.mp4",
    }

    fake_video = MagicMock(
        id=1,
        source_type="url",
        source_url="https://example.com/video",
        title="Ma vidéo",
        description=None,
        duration=120.0,
        status="pending",
    )
    mock_create_video.return_value = fake_video
    mock_create_job.return_value = MagicMock(id=7)

    response = client.post(
        "/videos/analyze-video",
        json={"url": "https://example.com/video"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == 7
    assert body["video"]["id"] == 1


@patch("app.api.routes.video.download_video")
def test_analyze_video_invalid_url_returns_400(mock_download, client):
    mock_download.side_effect = VideoIngestionError(
        "Impossible de récupérer la vidéo : 403 Forbidden"
    )

    response = client.post(
        "/videos/analyze-video",
        json={"url": "https://youtube.com/blocked"},
    )

    assert response.status_code == 400
    assert "403" in response.json()["detail"]


def test_analyze_video_missing_url_returns_422(client):
    response = client.post("/videos/analyze-video", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------
# POST /videos/analyze-video/upload
# ---------------------------------------------------------------

@patch("app.api.routes.video.generate_video_path")
def test_analyze_video_upload_empty_file_returns_400(mock_generate_path, client, tmp_path):
    fake_path = tmp_path / "empty.mp4"
    mock_generate_path.return_value = fake_path

    response = client.post(
        "/videos/analyze-video/upload",
        files={"file": ("empty.mp4", b"", "video/mp4")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


# ---------------------------------------------------------------
# GET /videos/{video_id}/status
# ---------------------------------------------------------------

@patch("app.api.routes.video.get_latest_job_for_video")
def test_status_endpoint_returns_404_for_unknown_video(mock_get_job, client):
    mock_get_job.return_value = None

    response = client.get("/videos/999/status")

    assert response.status_code == 404
    assert "No analysis job" in response.json()["detail"]


def test_status_endpoint_returns_422_for_non_integer_id(client):
    # Regression test: a frontend bug once sent "undefined" as the
    # video id (data.id instead of data.video.id), which silently
    # broke polling because the 422 was never surfaced to the user.
    response = client.get("/videos/undefined/status")

    assert response.status_code == 422


@patch("app.api.routes.video.get_latest_job_for_video")
def test_status_endpoint_returns_job_status(mock_get_job, client):
    mock_get_job.return_value = MagicMock(
        id=7,
        video_id=1,
        status="running",
        current_stage="diarization",
        error_message=None,
        created_at="2026-08-13T15:33:30",
        started_at="2026-08-13T15:33:31",
        completed_at=None,
    )

    response = client.get("/videos/1/status")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["current_stage"] == "diarization"


# ---------------------------------------------------------------
# GET /videos/{video_id}/result
# ---------------------------------------------------------------

def test_result_endpoint_returns_404_when_video_not_found(client, mock_db):
    mock_db.get.return_value = None

    response = client.get("/videos/999/result")

    assert response.status_code == 404
    assert "Video not found" in response.json()["detail"]


@patch("app.api.routes.video.get_analysis_result")
def test_result_endpoint_returns_404_when_analysis_not_ready(
    mock_get_result, client, mock_db
):
    mock_db.get.return_value = MagicMock(id=1, title="Ma vidéo", duration=120.0)
    mock_get_result.return_value = None

    response = client.get("/videos/1/result")

    assert response.status_code == 404
    assert "not available yet" in response.json()["detail"]


@patch("app.api.routes.video.get_analysis_result")
def test_result_endpoint_returns_full_payload(mock_get_result, client, mock_db):
    fake_video = MagicMock(id=1, title="Ma vidéo", duration=120.0)
    fake_result = MagicMock(
        number_of_speakers=2,
        summary="Résumé de test.",
        key_points=["Point 1", "Point 2"],
        topics=["Sujet 1"],
    )
    mock_db.get.return_value = fake_video
    mock_get_result.return_value = fake_result

    fake_segment = MagicMock(start=0.0, end=5.0, speaker="SPEAKER_01", text="Bonjour")
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        fake_segment
    ]

    response = client.get("/videos/1/result")

    assert response.status_code == 200
    body = response.json()
    assert body["number_of_speakers"] == 2
    assert body["transcript"][0]["speaker"] == "SPEAKER_01"



# ---------------------------------------------------------------
# POST /videos/{video_id}/retry
# ---------------------------------------------------------------

def test_retry_returns_404_when_video_not_found(client, mock_db):
    mock_db.get.return_value = None

    response = client.post("/videos/999/retry")

    assert response.status_code == 404
    assert "Video not found" in response.json()["detail"]


@patch("app.api.routes.video.get_latest_job_for_video")
def test_retry_returns_404_when_no_job_exists(mock_get_job, client, mock_db):
    mock_db.get.return_value = MagicMock(id=1, file_path="/app/storage/video.mp4")
    mock_get_job.return_value = None

    response = client.post("/videos/1/retry")

    assert response.status_code == 404
    assert "No analysis job" in response.json()["detail"]


@patch("app.api.routes.video.get_latest_job_for_video")
def test_retry_returns_409_when_job_still_running(mock_get_job, client, mock_db):
    mock_db.get.return_value = MagicMock(id=1, file_path="/app/storage/video.mp4")
    mock_get_job.return_value = MagicMock(status="running")

    response = client.post("/videos/1/retry")

    assert response.status_code == 409
    assert "Cannot retry" in response.json()["detail"]


@patch("app.api.routes.video.os.path.exists")
@patch("app.api.routes.video.get_latest_job_for_video")
def test_retry_returns_400_when_file_missing_on_disk(
    mock_get_job, mock_exists, client, mock_db
):
    mock_db.get.return_value = MagicMock(id=1, file_path="/app/storage/video.mp4")
    mock_get_job.return_value = MagicMock(status="failed")
    mock_exists.return_value = False

    response = client.post("/videos/1/retry")

    assert response.status_code == 400
    assert "no longer available" in response.json()["detail"]


@patch("app.api.routes.video.create_analysis_job")
@patch("app.api.routes.video.os.path.exists")
@patch("app.api.routes.video.get_latest_job_for_video")
def test_retry_success_creates_new_job(
    mock_get_job, mock_exists, mock_create_job, client, mock_db
):
    fake_video = MagicMock(
        id=1,
        file_path="/app/storage/video.mp4",
        source_type="url",
        source_url="https://example.com/video",
        title="Ma vidéo",
        description=None,
        duration=120.0,
        status="failed",
    )
    mock_db.get.return_value = fake_video
    mock_get_job.return_value = MagicMock(status="failed")
    mock_exists.return_value = True
    mock_create_job.return_value = MagicMock(id=42)

    response = client.post("/videos/1/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == 42
    assert fake_video.status == "pending"