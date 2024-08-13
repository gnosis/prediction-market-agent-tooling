from PIL.Image import Image as ImageType

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.image_gen.image_gen import generate_image
from prediction_market_agent_tooling.tools.langfuse_ import langfuse_context, observe


def rewrite_question_into_image_generation_prompt(
    question: str, enable_langfuse: bool = False
) -> str:
    try:
        from langchain_core.runnables.config import RunnableConfig
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "openai not installed, please install extras `langchain` to use this function."
        )
    llm = ChatOpenAI(
        model="gpt-4-turbo",
        temperature=0.0,
        api_key=APIKeys().openai_api_key_secretstr_v1,
    )
    config: RunnableConfig = {}
    if enable_langfuse:
        config["callbacks"] = [langfuse_context.get_current_langchain_handler()]
    rewritten = str(
        llm.invoke(
            f"Rewrite this prediction market question '{question}' into a form that will generate nice thumbnail with DALL-E-3."
            "The thumbnail should be catchy and visually appealing. With a large object in the center of the image.",
            config=config,
        ).content
    )
    return rewritten


def generate_image_for_market(
    question: str, enable_langfuse: bool = False
) -> ImageType:
    prompt = rewrite_question_into_image_generation_prompt(question, enable_langfuse)
    return generate_image(prompt)


@observe()
def generate_image_for_market_observed(question: str) -> ImageType:
    return generate_image_for_market(question, enable_langfuse=True)
