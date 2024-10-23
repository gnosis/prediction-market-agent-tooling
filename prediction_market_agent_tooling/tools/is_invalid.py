import tenacity

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.cache import persistent_inmemory_cache
from prediction_market_agent_tooling.tools.is_predictable import (
    parse_decision_yes_no_completion,
)
from prediction_market_agent_tooling.tools.langfuse_ import (
    get_langfuse_langchain_config,
    observe,
)
from prediction_market_agent_tooling.tools.utils import (
    LLM_SEED,
    LLM_SUPER_LOW_TEMPERATURE,
)

# I tried to make it return a JSON, but it didn't work well in combo with asking it to do chain of thought.
# Rules are almost copy-pasted from https://cdn.kleros.link/ipfs/QmZM12kkguXFk2C94ykrKpambt4iUVKsVsxGxDEdLS68ws/omen-rules.pdf,
# with some small prompting mods and I removed the point about "The outcome of the market must be known by its Resolution Date.", because that can not be verified before-hand.
# and also point about "in which none of the answers are valid will resolve as invalid" and "in which multiple answers are valid will resolve as invalid.", because before hand we can not know if one of the outcomes happened or not.
QUESTION_IS_INVALID_PROMPT = """Main signs about an invalid question (sometimes referred to as a "market"):
- The market's question is about immoral violence, death or assassination.
- The violent event can be caused by a single conscious being.
- The violent event is done illegally.
- The market should not directly incentivize immoral violent (such as murder, rape or unjust imprisonment) actions which could likely be performed by any participant.
- Invalid: Will Donald Trump be alive on the 01/12/2021? (Anyone could bet on "No" and kill him for a guaranteed profit. Anyone could bet on "Yes" to effectively put a bounty on his head).
- Invalid: Will Hera be a victim of swatting in 2020? (Anyone could falsely call the emergency services on him in order to win the bet)
- This does not prevent markets:
  - Whose topics are violent events not caused by conscious beings.
  - Valid: How many people will die from COVID19 in 2020? (Viruses don’t use prediction markets).
  - Whose main source of uncertainty is not related to a potential violent action.
  - Valid: Will Trump win the 2020 US presidential election? (The main source of uncertainty is the vote of US citizens, not a potential murder of a presidential candidate).
  - Which could give an incentive only to specific participants to commit an immoral violent action, but are in practice unlikely.
  - Valid: Will the US be engaged in a military conflict with a UN member state in 2021? (It’s unlikely for the US to declare war in order to win a bet on this market).
  - Valid: Will Derek Chauvin go to jail for the murder of George Flyod? (It’s unlikely that the jurors would collude to make a wrong verdict in order to win this market).
- Questions with relative dates will resolve as invalid. Dates must be stated in absolute terms, not relative depending on the current time.
- Invalid: Who will be the president of the United States in 6 months? ("in 6 months depends on the current time").
- Invalid: In the next 14 days, will Gnosis Chain gain another 1M users? ("in the next 14 days depends on the current time").
- Questions about moral values and not facts will be resolved as invalid.
- Invalid: "Is it ethical to eat meat?".

Follow a chain of thought to evaluate if the question is invalid:

First, write the parts of the following question:

"{question}"

Then, write down what is the future event of the question, what it refers to and when that event will happen if the question contains it.

Then, explain why do you think it is or isn't invalid.

Finally, write your final decision, write `decision: ` followed by either "yes it is invalid" or "no it isn't invalid" about the question. Don't write anything else after that. You must include "yes" or "no".
"""


@persistent_inmemory_cache
@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
@observe()
def is_invalid(
    question: str,
    engine: str = "gpt-4o",
    temperature: float = LLM_SUPER_LOW_TEMPERATURE,
    seed: int = LLM_SEED,
    prompt_template: str = QUESTION_IS_INVALID_PROMPT,
    max_tokens: int = 1024,
) -> bool:
    """
    Evaluate if the question is actually answerable.
    """
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.error("langchain not installed, skipping is_invalid")
        return True

    llm = ChatOpenAI(
        model=engine,
        temperature=temperature,
        seed=seed,
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
