from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult


def get_analysis_result(
    db: Session,
    video_id: int,
) -> AnalysisResult | None:
    return (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.video_id == video_id
        )
        .first()
    )