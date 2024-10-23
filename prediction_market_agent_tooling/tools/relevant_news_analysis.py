from datetime import datetime, timedelta

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.langfuse_ import (
    get_langfuse_langchain_config,
    observe,
)
from prediction_market_agent_tooling.tools.tavily.tavily_models import TavilyResult
from prediction_market_agent_tooling.tools.tavily.tavily_search import (
    get_relevant_news_since,
)
from prediction_market_agent_tooling.tools.tavily.tavily_storage import TavilyStorage
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow


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
    url: str
    summary: str
    relevance_reasoning: str

    @staticmethod
    def from_tavily_result_and_analysis(
        taviy_result: TavilyResult,
        relevant_news_analysis: RelevantNewsAnalysis,
    ) -> "RelevantNews":
        return RelevantNews(
            url=taviy_result.url,
            summary=taviy_result.content,
            relevance_reasoning=relevant_news_analysis.reasoning,
        )


SUMMARISE_RELEVANT_NEWS_PROMPT_TEMPLATE = """
You are an expert news analyst, tracking stories that may affect your prediction to the outcome of a particular QUESTION.

Your role is to identify only the relevant information from a scraped news site (RAW_CONTENT), analyse it, and determine whether it contains developments or announcements occuring **after** the DATE_OF_INTEREST that could affect the outcome of the QUESTION.

Note that the news article may be published after the DATE_OF_INTEREST, but reference information that is older than the DATE_OF_INTEREST.

[QUESTION]
{question}

[DATE_OF_INTEREST]
{date_of_interest}

[RAW_CONTENT]
{raw_content}

For your analysis, you should:
- Discard the 'noise' from the raw content (e.g. ads, irrelevant content)
- Consider ONLY information that would have a noteable impact on the outcome of the question.
- Consider ONLY information relating to an announcement or development that occured **after** the DATE_OF_INTEREST.
- Present this information concisely in your reasoning.
- In your reasoning, do not use the term 'DATE_OF_INTEREST' directly. Use the actual date you are referring to instead.
- In your reasoning, do not use the term 'RAW_CONTENT' directly. Refer to it as 'the article', or quote the content you are referring to.

{format_instructions}
"""


@observe()
def analyse_news_relevance(
    raw_content: str,
    question: str,
    date_of_interest: datetime,
    model: str,
    temperature: float,
) -> RelevantNewsAnalysis:
    """
    Analyse whether the news contains new (relative to the given date)
    information relevant to the given question.
    """
    parser = PydanticOutputParser(pydantic_object=RelevantNewsAnalysis)
    prompt = PromptTemplate(
        template=SUMMARISE_RELEVANT_NEWS_PROMPT_TEMPLATE,
        input_variables=["question"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    llm = ChatOpenAI(
        temperature=temperature,
        model=model,
        api_key=APIKeys().openai_api_key_secretstr_v1,
    )
    chain = prompt | llm | parser

    relevant_news_analysis: RelevantNewsAnalysis = chain.invoke(
        {
            "raw_content": raw_content,
            "question": question,
            "date_of_interest": str(date_of_interest),
        },
        config=get_langfuse_langchain_config(),
    )
    return relevant_news_analysis


@observe()
def get_certified_relevant_news_since(
    question: str,
    days_ago: int,
    model: str = "gpt-4o",
    temperature: float = 0.0,
    max_search_results: int = 3,
    tavily_storage: TavilyStorage | None = None,
) -> RelevantNews | None:
    """
    Get relevant news since a given date for a given question. Retrieves
    possibly relevant news from tavily, then checks that it is relevant via
    an LLM call.

    TODO save/restore from a cache
    TODO generate subquestions and get relevant news for each
    """
    results = get_relevant_news_since(
        question=question,
        days_ago=days_ago,
        score_threshold=0.0,  # Be conservative to avoid missing relevant information
        max_results=max_search_results,
        tavily_storage=tavily_storage,
    )

    # Sort results by descending 'relevance score' to maximise the chance of
    # finding relevant news early
    results = sorted(
        results,
        key=lambda result: result.score,
        reverse=True,
    )

    for result in results:
        relevant_news_analysis = analyse_news_relevance(
            raw_content=check_not_none(result.raw_content),
            question=question,
            date_of_interest=utcnow() - timedelta(days=days_ago),
            model=model,
            temperature=temperature,
        )

        # Return first relevant news found
        if relevant_news_analysis.contains_relevant_news:
            return RelevantNews.from_tavily_result_and_analysis(
                taviy_result=result,
                relevant_news_analysis=relevant_news_analysis,
            )

    # No relevant news found
    return None
