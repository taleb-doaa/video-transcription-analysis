from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.transcript_segment import TranscriptSegment


def save_transcript_segments(
    db: Session,
    video_id: int,
    segments: list[dict],
) -> list[TranscriptSegment]:
    """
    Replace the existing transcription of a video
    with the newly generated Whisper segments.
    """

    # Remove previous transcription for this video.
    db.execute(
        delete(TranscriptSegment).where(
            TranscriptSegment.video_id == video_id
        )
    )

    saved_segments = []

    for segment in segments:
        transcript_segment = TranscriptSegment(
            video_id=video_id,
            start=segment["start"],
            end=segment["end"],
            text=segment["text"],
            speaker=segment.get("speaker"),
        )

        db.add(transcript_segment)
        saved_segments.append(transcript_segment)

    db.commit()

    for segment in saved_segments:
        db.refresh(segment)

    return saved_segments