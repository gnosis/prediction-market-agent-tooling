from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.langfuse_ import (
    get_langfuse_langchain_config,
    observe,
)


@observe()
def infer_category(
    question: str,
    categories: set[str],
    model: str = "gpt-3.5-turbo-0125",
) -> str:
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain.schema.output_parser import StrOutputParser
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "openai not installed, please install extras `langchain` to use this function."
        )
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
            api_key=APIKeys().openai_api_key_secretstr_v1,
        )
        | StrOutputParser()
    )

    response: str = research_evaluation_chain.invoke(
        {"question": question, "categories": sorted(categories)},
        config=get_langfuse_langchain_config(),
    )

    formatted = response.strip().strip("'").strip('"').strip()

    return formatted
