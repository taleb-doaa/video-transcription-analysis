import pytest
from pydantic import ValidationError

from app.schemas.video import VideoURLRequest


def test_video_url_request_accepts_valid_url():
    request = VideoURLRequest(url="https://example.com/video")
    assert request.url == "https://example.com/video"


def test_video_url_request_rejects_empty_url():
    with pytest.raises(ValidationError):
        VideoURLRequest(url="")


def test_video_url_request_rejects_missing_url():
    with pytest.raises(ValidationError):
        VideoURLRequest()