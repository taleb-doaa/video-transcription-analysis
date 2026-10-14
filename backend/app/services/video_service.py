from pathlib import Path
from typing import Any

import yt_dlp

from app.services.storage_service import generate_video_path


class VideoIngestionError(Exception):
    pass


def download_video(url: str) -> dict[str, Any]:
    output_path = generate_video_path()

    ydl_opts = {
        "outtmpl": str(output_path),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if not output_path.exists():
            raise VideoIngestionError(
                "La vidéo a été téléchargée mais le fichier est introuvable."
            )

        return {
            "file_path": str(output_path),
            "title": info.get("title"),
            "description": info.get("description"),
            "duration": info.get("duration"),
            "source_url": url,
            "source_type": "url",
        }

    except Exception as exc:
        if output_path.exists():
            output_path.unlink()

        raise VideoIngestionError(
            f"Impossible de récupérer la vidéo : {exc}"
        ) from exc