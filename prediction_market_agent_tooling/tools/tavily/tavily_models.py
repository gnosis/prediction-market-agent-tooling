from pydantic import BaseModel


class TavilyResult(BaseModel):
    title: str
    url: str
    content: str
    score: float
    raw_content: str | None
    published_date: str | None = None


class TavilyResponse(BaseModel):
    query: str
    follow_up_questions: str | None = None
    answer: str | None
    images: list[str]
    results: list[TavilyResult]
    response_time: float
