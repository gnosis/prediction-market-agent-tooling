import tenacity

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache
from prediction_market_agent_tooling.tools.langfuse_ import (
    get_langfuse_langchain_config,
    observe,
)
from prediction_market_agent_tooling.tools.utils import (
    LLM_SEED,
    LLM_SUPER_LOW_TEMPERATURE,
)

REPHRASE_QUESTION_PROMPT = """Given the following question of main interest: {question}

But it's conditioned on `{parent_question}` resolving to `{needed_parent_outcome}`.

Rewrite the main question to contain the parent question in the correct form. 

The main question will be used as a prediction market, so it does need to be rephrased using the parent question properly. Such that the probability of the main question also accounts for the conditioned outcome.

For example:
```
Main question: What is the probability of <X> happening before <date>?
Conditioned on: Will <Y> happen before <another-date>?
Rephrased: What is the joint probability of Y happening before <another-date> and then X happening before <date>?
```

Output only the rephrased question.
"""


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
@observe()
@db_cache
def rephrase_question_to_unconditional(
    question: str,
    parent_question: str,
    needed_parent_outcome: str,
    engine: str = "gpt-4.1",
    temperature: float = LLM_SUPER_LOW_TEMPERATURE,
    seed: int = LLM_SEED,
    prompt_template: str = REPHRASE_QUESTION_PROMPT,
    max_tokens: int = 1024,
) -> str:
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError("langchain not installed")

    llm = ChatOpenAI(
        model_name=engine,
        temperature=temperature,
        seed=seed,
        openai_api_key=APIKeys().openai_api_key,
    )

    prompt = ChatPromptTemplate.from_template(template=prompt_template)
    messages = prompt.format_messages(
        question=question,
        parent_question=parent_question,
        needed_parent_outcome=needed_parent_outcome,
    )
    completion = str(
        llm.invoke(
            messages, max_tokens=max_tokens, config=get_langfuse_langchain_config()
        ).content
    )

    return completion
