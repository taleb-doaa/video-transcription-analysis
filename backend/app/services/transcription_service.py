import os
from typing import Any

from faster_whisper import WhisperModel


MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")


class TranscriptionService:
    def __init__(self):
        self.model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(
                f"Audio file not found: {audio_path}"
            )

        segments, info = self.model.transcribe(
            audio_path,
            task="transcribe",
            word_timestamps=False,
            vad_filter=True,
            beam_size=5,
        )

        transcript = []

        for segment in segments:
            text = segment.text.strip()

            if not text:
                continue

            transcript.append(
                {
                    "start": round(float(segment.start), 3),
                    "end": round(float(segment.end), 3),
                    "text": text,
                }
            )

        if not transcript:
            raise ValueError(
                "No speech detected in the audio."
            )

        return {
            "language": info.language,
            "language_probability": round(
                float(info.language_probability), 4
            ),
            "segments": transcript,
        }


_transcription_service = None


def get_transcription_service() -> TranscriptionService:
    global _transcription_service

    if _transcription_service is None:
        _transcription_service = TranscriptionService()

    return _transcription_service


def transcribe_audio(audio_path: str) -> dict[str, Any]:
    service = get_transcription_service()
    return service.transcribe(audio_path)