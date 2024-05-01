from loguru import logger

from prediction_market_agent_tooling.tools.cache import persistent_inmemory_cache

# I tried to make it return a JSON, but it didn't work well in combo with asking it to do chain of thought.
QUESTION_IS_PREDICTABLE_BINARY_PROMPT = """Main signs about a fully qualified question (sometimes referred to as a "market"):
- The market's question needs to be specific, without use of pronouns.
- The market's question needs to have a clear future event.
- The market's question needs to have a clear time frame.
- The event in the market's question doesn't have to be ultra-specific, it will be decided by a crowd later on.
- If the market's question contains date, but without an year, it's okay.
- If the market's question contains year, but without an exact date, it's okay.
- The market's question can not be about itself or refer to itself.
- The answer is probably Google-able, after the event happened.
- The potential asnwer can be only "Yes" or "No".

Follow a chain of thought to evaluate if the question is fully qualified:

First, write the parts of the following question:

"{question}"

Then, write down what is the future event of the question, what it refers to and when that event will happen if the question contains it.

Then, explain why do you think it is or isn't fully qualified.

Finally, write your final decision, write `decision: ` followed by either "yes it is fully qualified" or "no it isn't fully qualified" about the question. Don't write anything else after that. You must include "yes" or "no".
"""


@persistent_inmemory_cache
def is_predictable_binary(
    question: str,
    engine: str = "gpt-4-1106-preview",
    prompt_template: str = QUESTION_IS_PREDICTABLE_BINARY_PROMPT,
) -> bool:
    """
    Evaluate if the question is actually answerable.
    """
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.info("langchain not installed, skipping is_predictable_binary")
        return True

    llm = ChatOpenAI(model=engine, temperature=0.0)

    prompt = ChatPromptTemplate.from_template(template=prompt_template)
    messages = prompt.format_messages(question=question)
    completion = str(llm(messages, max_tokens=512).content)

    try:
        decision = completion.lower().rsplit("decision", 1)[1]
    except IndexError as e:
        raise ValueError(
            f"Invalid completion in is_predictable for `{question}`: {completion}"
        ) from e

    if "yes" in decision:
        is_predictable = True
    elif "no" in decision:
        is_predictable = False
    else:
        raise ValueError(
            f"Invalid completion in is_predictable for `{question}`: {completion}"
        )

    return is_predictable
