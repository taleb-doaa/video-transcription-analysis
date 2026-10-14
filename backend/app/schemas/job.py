from datetime import datetime

from pydantic import BaseModel

from app.schemas.video import VideoResponse


class JobStatusResponse(BaseModel):
    id: int
    video_id: int
    status: str
    current_stage: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {
        "from_attributes": True,
    }


class AnalyzeVideoResponse(BaseModel):
    video: VideoResponse
    job_id: int