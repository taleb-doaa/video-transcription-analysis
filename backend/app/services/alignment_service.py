from typing import Any


def merge_speakers(
    transcript_segments: list[dict[str, Any]],
    diarization_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Assign a speaker to each transcript segment based on the
    diarization segment with which it overlaps the most in time.

    If no diarization segment overlaps a transcript segment,
    the speaker is left as None rather than guessed.
    """

    merged = []

    for segment in transcript_segments:
        best_speaker = None
        best_overlap = 0.0

        for diarization_segment in diarization_segments:
            overlap = min(
                segment["end"], diarization_segment["end"]
            ) - max(
                segment["start"], diarization_segment["start"]
            )

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diarization_segment["speaker"]

        merged.append({**segment, "speaker": best_speaker})

    return merged