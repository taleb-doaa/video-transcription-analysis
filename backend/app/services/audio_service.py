import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    pass


def extract_audio(
    video_path: str,
    output_path: str,
    sample_rate: int = 16000,
    channels: int = 1,
) -> str:
    """
    Extract audio from a video and convert it to:
    - WAV
    - PCM signed 16-bit
    - mono
    - 16 kHz by default
    """

    video = Path(video_path)
    output = Path(output_path)

    if not video.exists():
        raise AudioExtractionError(
            f"Video file does not exist: {video_path}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output),
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AudioExtractionError(
            f"FFmpeg audio extraction failed:\n{exc.stderr}"
        ) from exc

    if not output.exists() or output.stat().st_size == 0:
        raise AudioExtractionError(
            "Audio extraction produced an empty file."
        )

    return str(output)