import tenacity

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache
from prediction_market_agent_tooling.tools.langfuse_ import (
    get_langfuse_langchain_config,
    observe,
)
from prediction_market_agent_tooling.tools.utils import (
    LLM_SEED,
    LLM_SUPER_LOW_TEMPERATURE,
)

# I tried to make it return a JSON, but it didn't work well in combo with asking it to do chain of thought.
QUESTION_IS_PREDICTABLE_BINARY_PROMPT = """Main signs about a fully qualified question (sometimes referred to as a "market"):
- The market's question needs to be specific, without use of pronouns.
- The market must refer to a future event — not something that already happened. This is a hard requirement. If the event has already occurred, the question is not fully qualified, even if it is specific and answerable.
- The market's question needs to have a clear time frame.
- The event in the market's question doesn't have to be ultra-specific, it will be decided by a crowd later on.
- If the market's question contains date, but without an year, it's okay.
- If the market's question contains year, but without an exact date, it's okay.
- The market's question can not be about itself or refer to itself.
- The answer is probably Google-able, after the event happened.

Follow a chain of thought to evaluate if the question is fully qualified:

First, write the parts of the following question:

"{question}"

Then, write down what is the future event of the question, what it refers to and when that event will happen if the question contains it.

Then, explain why do you think it is or isn't fully qualified.

Finally, write your final decision, write `decision: ` followed by either "yes it is fully qualified" or "no it isn't fully qualified" about the question. Don't write anything else after that. You must include "yes" or "no".
"""

QUESTION_IS_PREDICTABLE_WITHOUT_DESCRIPTION_PROMPT = """Main signs about a fully self-contained question (sometimes referred to as a "market"):
- Description of the question can not contain any additional information required to answer the question.

For the question:

```
{question}
```

And the description:

```
{description}
```

Description refers only to the text above and nothing else. 

Even if the question is somewhat vague, but even the description does not contain enough of extra information, it's okay and the question is fully self-contained. 
If the question is vague and the description contains the information required to answer the question, it's not fully self-contained and the answer is "no".

Follow a chain of thought to evaluate if the question doesn't need the description to be answered.

Start by examining the question and the description in detail. Write down their parts, what they refer to and what they contain. 

Continue by writing comparison of the question and the description content. Write down what the question contains and what the description contains.

Explain, why do you think it does or doesn't need the description.

Description can contain additional information, but it can not contain any information required to answer the question.

Description can contain additional information about the exact resolution criteria, but the question should be answerable even without it.

As long as the question contains some time frame, it's okay if the description only specifies it in more detail.

Description usually contains the question in more detailed form, but the question on its own should be answerable.

For example, that means, description can not contain date if question doesn't contain it. Description can not contain target if the question doesn't contain it, etc.

Finally, write your final decision, write `decision: ` followed by either "yes it is fully self-contained" or "no it isn't fully self-contained" about the question. Don't write anything else after that. You must include "yes" or "no".
"""


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
@observe()
@db_cache
def is_predictable_binary(
    question: str,
    engine: str = "gpt-4o-2024-08-06",
    prompt_template: str = QUESTION_IS_PREDICTABLE_BINARY_PROMPT,
    max_tokens: int = 1024,
) -> bool:
    """
    Evaluate if the question is actually answerable.
    """
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.error("langchain not installed, skipping is_predictable_binary")
        return True

    llm = ChatOpenAI(
        model=engine,
        temperature=LLM_SUPER_LOW_TEMPERATURE,
        seed=LLM_SEED,
        api_key=APIKeys().openai_api_key_secretstr_v1,
    )

    prompt = ChatPromptTemplate.from_template(template=prompt_template)
    messages = prompt.format_messages(question=question)
    completion = str(
        llm.invoke(
            messages, max_tokens=max_tokens, config=get_langfuse_langchain_config()
        ).content
    )

    return parse_decision_yes_no_completion(question, completion)


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
@observe()
@db_cache
def is_predictable_without_description(
    question: str,
    description: str,
    engine: str = "gpt-4o-2024-08-06",
    prompt_template: str = QUESTION_IS_PREDICTABLE_WITHOUT_DESCRIPTION_PROMPT,
    max_tokens: int = 1024,
) -> bool:
    """
    Evaluate if the question is fully self-contained.
    """
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.error(
            "langchain not installed, skipping is_predictable_without_description"
        )
        return True

    llm = ChatOpenAI(
        model=engine,
        temperature=LLM_SUPER_LOW_TEMPERATURE,
        seed=LLM_SEED,
        api_key=APIKeys().openai_api_key_secretstr_v1,
    )

    prompt = ChatPromptTemplate.from_template(template=prompt_template)
    messages = prompt.format_messages(
        question=question,
        description=description,
    )
    completion = str(
        llm.invoke(
            messages, max_tokens=max_tokens, config=get_langfuse_langchain_config()
        ).content
    )

    return parse_decision_yes_no_completion(question, completion)


def parse_decision_yes_no_completion(question: str, completion: str) -> bool:
    logger.debug(completion)
    try:
        decision = completion.lower().rsplit("decision", 1)[1]
    except IndexError as e:
        raise ValueError(f"Invalid completion for `{question}`: {completion}") from e

    if "yes" in decision:
        return True
    elif "no" in decision:
        return False
    else:
        raise ValueError(f"Invalid completion for `{question}`: {completion}")
