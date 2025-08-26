MARKET_TYPE_KEY = "market_type"
REPOSITORY_KEY = "repository"
OWNER_KEY = "owner"
INVALID_OUTCOME_LOWERCASE_IDENTIFIER = "invalid"
# Market-agnostic outcome identifiers
YES_OUTCOME_LOWERCASE_IDENTIFIER = "yes"
NO_OUTCOME_LOWERCASE_IDENTIFIER = "no"
UP_OUTCOME_LOWERCASE_IDENTIFIER = "up"
DOWN_OUTCOME_LOWERCASE_IDENTIFIER = "down"


def is_invalid_outcome(outcome: str) -> bool:
    return INVALID_OUTCOME_LOWERCASE_IDENTIFIER in outcome.lower()
