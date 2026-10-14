import os
from typing import Any

from pyannote.audio import Pipeline

from app.core.config import settings

MODEL_NAME = "pyannote/speaker-diarization-3.1"

HF_TOKEN = settings.hf_token


class DiarizationService:

    def __init__(self):
        if not HF_TOKEN:
            raise ValueError(
                "HF_TOKEN is not configured."
            )

        self.pipeline = Pipeline.from_pretrained(
            MODEL_NAME,
            token=HF_TOKEN,
        )

    def diarize(
        self,
        audio_path: str,
    ) -> list[dict[str, Any]]:

        if not os.path.exists(audio_path):
            raise FileNotFoundError(
                f"Audio file not found: {audio_path}"
            )

        output = self.pipeline(audio_path)

        diarization = output.speaker_diarization

        segments = []

        for turn, _, speaker in diarization.itertracks(
            yield_label=True
        ):
            segments.append(
                {
                    "start": round(float(turn.start), 3),
                    "end": round(float(turn.end), 3),
                    "speaker": speaker,
                }
            )

        return segments


_diarization_service = None


def get_diarization_service() -> DiarizationService:

    global _diarization_service

    if _diarization_service is None:
        _diarization_service = DiarizationService()

    return _diarization_service


def diarize_audio(
    audio_path: str,
) -> list[dict[str, Any]]:

    service = get_diarization_service()

    return service.diarize(audio_path)