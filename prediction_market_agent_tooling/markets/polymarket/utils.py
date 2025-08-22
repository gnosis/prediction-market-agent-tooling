from prediction_market_agent_tooling.markets.market_type import MarketType
from prediction_market_agent_tooling.tools.google_utils import search_google_gcp


def find_url_to_polymarket(question: str) -> str | None:
    # Manually create potential Polymarket's slug from the question.
    replace_chars = {
        ":": "",
        "’": "",
        "“": "",
        "$": "",
        " ": "-",
    }
    slug = "".join(replace_chars.get(char, char) for char in question.lower())

    # Search for the links to the Polymarket's market page on Google.
    links = search_google_gcp(
        # For some reason, just giving it in the query works better than using `site_search`, `exact_terms` or other parameters of the google search.
        query=f"{MarketType.POLYMARKET.market_class.base_url} {question}",
        num=10,
    )

    for link in links:
        link_slug = link.split("/")[-1]

        # If the link is from Polymarket and the slug is in the link, we assume it's the right market.
        if (
            MarketType.POLYMARKET.market_class.base_url in link
            and link_slug
            # Only `startswith`, because long questions get truncated in the slug.
            and slug.startswith(link_slug)
        ):
            return link

    return None
