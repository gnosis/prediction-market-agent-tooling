from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain_openai import ChatOpenAI

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import secretstr_to_v1_secretstr


def infer_category(
    question: str, categories: set[str], model: str = "gpt-3.5-turbo-0125"
) -> str:
    prompt = ChatPromptTemplate.from_template(
        template="""Assign the following question: {question}

To one of these categories: {categories}

Write only the category itself, nothing else.
"""
    )

    research_evaluation_chain = (
        prompt
        | ChatOpenAI(
            model=model,
            api_key=secretstr_to_v1_secretstr(APIKeys().openai_api_key),
        )
        | StrOutputParser()
    )

    response: str = research_evaluation_chain.invoke(
        {"question": question, "categories": sorted(categories)}
    )

    formatted = response.strip().strip("'").strip('"').strip()

    return formatted
