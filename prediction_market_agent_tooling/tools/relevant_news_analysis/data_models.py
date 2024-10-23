from pydantic import BaseModel, Field

from prediction_market_agent_tooling.tools.tavily.tavily_models import TavilyResult


class RelevantNewsAnalysis(BaseModel):
    reasoning: str = Field(
        ...,
        description="The reason why the news contains information relevant to the given question. Or if no news is relevant, why not.",
    )
    contains_relevant_news: bool = Field(
        ...,
        description="A boolean flag for whether the news contains information relevant to the given question.",
    )


class RelevantNews(BaseModel):
    question: str
    url: str
    summary: str
    relevance_reasoning: str
    days_ago: int

    @staticmethod
    def from_tavily_result_and_analysis(
        question: str,
        days_ago: int,
        taviy_result: TavilyResult,
        relevant_news_analysis: RelevantNewsAnalysis,
    ) -> "RelevantNews":
        return RelevantNews(
            question=question,
            url=taviy_result.url,
            summary=taviy_result.content,
            relevance_reasoning=relevant_news_analysis.reasoning,
            days_ago=days_ago,
        )


class NoRelevantNews(BaseModel):
    """
    A placeholder model for when no relevant news is found. Enables ability to
    distinguish between 'a cache hit with no news' and 'a cache miss'.
    """

    pass
