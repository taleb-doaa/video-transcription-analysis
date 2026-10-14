from pydantic import BaseModel, Field


class VideoURLRequest(BaseModel):
    url: str = Field(..., min_length=1)


class VideoResponse(BaseModel):
    id: int
    source_type: str
    source_url: str | None
    title: str | None
    description: str | None
    duration: float | None
    status: str

    model_config = {
        "from_attributes": True,
    }