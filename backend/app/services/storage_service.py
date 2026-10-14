from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def get_storage_dir() -> Path:
    path = Path(settings.storage_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_video_path(extension: str = ".mp4") -> Path:
    filename = f"{uuid4().hex}{extension}"
    return get_storage_dir() / filename


def generate_audio_path() -> Path:
    filename = f"{uuid4().hex}.wav"
    return get_storage_dir() / filename