from pydantic import BaseModel, Field
from typing import Literal

class SourceRequest(BaseModel):
    url: str

class AnalysisRequest(BaseModel):
    project_id: str
    count: int = Field(ge=1, le=50)
    duration: int = Field(ge=10, le=180)
    sensitivity: Literal["relaxed", "balanced", "sensitive"] = "balanced"
    categories: list[str] = Field(min_length=1)
    gemini_key: str | None = None
    model: str | None = None

class ClipPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    hashtags: list[str] | None = None
    captions: list[dict] | None = None

