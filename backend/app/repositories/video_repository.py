from sqlalchemy.orm import Session

from app.models.video import Video


def create_video(
    db: Session,
    *,
    source_type: str,
    source_url: str | None,
    title: str | None,
    description: str | None,
    duration: float | None,
    file_path: str | None,
) -> Video:

    video = Video(
        source_type=source_type,
        source_url=source_url,
        title=title,
        description=description,
        duration=duration,
        file_path=file_path,
        status="pending",
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    return video