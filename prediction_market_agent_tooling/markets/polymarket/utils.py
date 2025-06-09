from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.polymarket.data_models_web import (
    PolymarketFullMarket,
)
from prediction_market_agent_tooling.tools.google_utils import search_google_gcp


def find_resolution_on_polymarket(question: str) -> Resolution | None:
    full_market = find_full_polymarket(question)
    # TODO: Only main markets are supported right now, add logic for others if needed.
    return (
        full_market.main_market.resolution
        if full_market and full_market.is_main_market
        else None
    )


def find_full_polymarket(question: str) -> PolymarketFullMarket | None:
    polymarket_url = find_url_to_polymarket(question)
    return (
        PolymarketFullMarket.fetch_from_url(polymarket_url) if polymarket_url else None
    )


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
