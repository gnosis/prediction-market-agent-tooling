from PIL.Image import Image as ImageType

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.image_gen.image_gen import generate_image
from prediction_market_agent_tooling.tools.langfuse_ import (
    get_langfuse_langchain_config,
    observe,
)


@observe()
def rewrite_question_into_image_generation_prompt(question: str) -> str:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "openai not installed, please install extras `langchain` to use this function."
        )
    llm = ChatOpenAI(
        model_name="gpt-4o-2024-08-06",
        temperature=0.0,
        openai_api_key=APIKeys().openai_api_key,
    )
    rewritten = str(
        llm.invoke(
            f"Rewrite this prediction market question '{question}' into a form that will generate nice thumbnail with DALL-E-3."
            "The thumbnail should be catchy and visually appealing. With a large object in the center of the image.",
            config=get_langfuse_langchain_config(),
        ).content
    )
    return rewritten


def generate_image_for_market(question: str) -> ImageType:
    prompt = rewrite_question_into_image_generation_prompt(question)
    return generate_image(prompt)
