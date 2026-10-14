from pydantic import BaseModel


class AnalysisResultResponse(BaseModel):
    id: int
    video_id: int
    number_of_speakers: int | None = None
    summary: str | None = None
    key_points: list[str] | None = None
    topics: list[str] | None = None

    model_config = {
        "from_attributes": True,
    }