from pydantic import BaseModel, Field


class BookSchema(BaseModel):
    title: str = Field(..., min_length=1)
    authors: list[str] = Field(default_factory=list)
    description: str | None = None
    cover_url: str | None = None
    google_id: str = Field(..., min_length=1)
