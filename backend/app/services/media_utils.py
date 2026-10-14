import json
import subprocess


def get_video_duration(file_path: str) -> float | None:
    """
    Return the duration (in seconds) of a local media file using ffprobe.
    Returns None if the duration cannot be determined.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        data = json.loads(result.stdout)
        duration = data.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None