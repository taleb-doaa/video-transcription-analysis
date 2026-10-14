from unittest.mock import MagicMock, patch

import pytest

from app.services.video_service import VideoIngestionError, download_video


@patch("app.services.video_service.generate_video_path")
@patch("app.services.video_service.yt_dlp.YoutubeDL")
def test_download_video_success(mock_ydl_class, mock_generate_path, tmp_path):
    fake_output = tmp_path / "video.mp4"
    fake_output.write_bytes(b"fake video content")
    mock_generate_path.return_value = fake_output

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.return_value = {
        "title": "Ma vidéo test",
        "description": "Une description",
        "duration": 120.5,
    }
    mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

    result = download_video("https://example.com/video")

    assert result["title"] == "Ma vidéo test"
    assert result["duration"] == 120.5
    assert result["source_type"] == "url"
    assert result["source_url"] == "https://example.com/video"
    assert result["file_path"] == str(fake_output)


@patch("app.services.video_service.generate_video_path")
@patch("app.services.video_service.yt_dlp.YoutubeDL")
def test_download_video_raises_ingestion_error_on_failure(
    mock_ydl_class, mock_generate_path, tmp_path
):
    fake_output = tmp_path / "video.mp4"
    mock_generate_path.return_value = fake_output

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.side_effect = Exception("HTTP Error 403: Forbidden")
    mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

    with pytest.raises(VideoIngestionError) as exc_info:
        download_video("https://youtube.com/some-blocked-video")

    assert "403" in str(exc_info.value)


@patch("app.services.video_service.generate_video_path")
@patch("app.services.video_service.yt_dlp.YoutubeDL")
def test_download_video_cleans_up_partial_file_on_failure(
    mock_ydl_class, mock_generate_path, tmp_path
):
    fake_output = tmp_path / "video.mp4"
    fake_output.write_bytes(b"partial content")
    mock_generate_path.return_value = fake_output

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.side_effect = Exception("network error")
    mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

    with pytest.raises(VideoIngestionError):
        download_video("https://example.com/video")

    assert not fake_output.exists()


@patch("app.services.video_service.generate_video_path")
@patch("app.services.video_service.yt_dlp.YoutubeDL")
def test_download_video_raises_when_file_missing_after_download(
    mock_ydl_class, mock_generate_path, tmp_path
):
    fake_output = tmp_path / "video.mp4"
    # Le fichier n'est jamais créé sur le disque.
    mock_generate_path.return_value = fake_output

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.return_value = {"title": "x"}
    mock_ydl_class.return_value.__enter__.return_value = mock_ydl_instance

    with pytest.raises(VideoIngestionError) as exc_info:
        download_video("https://example.com/video")

    assert "introuvable" in str(exc_info.value)