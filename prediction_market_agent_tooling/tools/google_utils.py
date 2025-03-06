import typing as t
from datetime import timedelta

import requests
import tenacity
from googleapiclient.discovery import build

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache


@tenacity.retry(
    wait=tenacity.wait_fixed(1),
    stop=tenacity.stop_after_attempt(3),
    after=lambda x: logger.debug(f"search_google_gcp failed, {x.attempt_number=}."),
)
@db_cache(max_age=timedelta(days=1))
def search_google_gcp(
    query: str | None = None,
    num: int = 3,
    exact_terms: str | None = None,
    exclude_terms: str | None = None,
    link_site: str | None = None,
    site_search: str | None = None,
    site_search_filter: t.Literal["e", "i"] | None = None,
) -> list[str]:
    """Search Google using a custom search engine."""
    keys = APIKeys()
    service = build(
        "customsearch", "v1", developerKey=keys.google_search_api_key.get_secret_value()
    )
    # See https://developers.google.com/custom-search/v1/reference/rest/v1/cse/list
    params: dict[str, str | int | None] = dict(
        q=query,
        cx=keys.google_search_engine_id.get_secret_value(),
        num=num,
        exactTerms=exact_terms,
        excludeTerms=exclude_terms,
        linkSite=link_site,
        siteSearch=site_search,
        siteSearchFilter=site_search_filter,
    )
    params_without_optional = {k: v for k, v in params.items() if v is not None}
    search = service.cse().list(**params_without_optional).execute()

    try:
        return (
            [result["link"] for result in search["items"]]
            if int(search["searchInformation"]["totalResults"]) > 0
            else []
        )
    except KeyError as e:
        raise ValueError(f"Can not parse results: {search}") from e


@tenacity.retry(
    wait=tenacity.wait_fixed(1),
    stop=tenacity.stop_after_attempt(3),
    after=lambda x: logger.debug(f"search_google_serper failed, {x.attempt_number=}."),
)
@db_cache(max_age=timedelta(days=1))
def search_google_serper(q: str) -> list[str]:
    """Search Google using the Serper API."""
    url = "https://google.serper.dev/search"
    response = requests.post(
        url,
        headers={
            "X-API-KEY": APIKeys().serper_api_key.get_secret_value(),
            "Content-Type": "application/json",
        },
        json={"q": q},
    )
    response.raise_for_status()
    parsed = response.json()
    return [x["link"] for x in parsed["organic"] if x.get("link")]
