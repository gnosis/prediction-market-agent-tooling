import json
import typing as t
from datetime import timedelta

import tenacity
from google.cloud import secretmanager
from googleapiclient.discovery import build
from pydantic import SecretStr

from prediction_market_agent_tooling.config import APIKeys, CloudCredentials
from prediction_market_agent_tooling.gtypes import PrivateKey
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache


@tenacity.retry(
    wait=tenacity.wait_fixed(1),
    stop=tenacity.stop_after_attempt(3),
    after=lambda x: logger.debug(f"search_google failed, {x.attempt_number=}."),
)
@db_cache(max_age=timedelta(days=1))
def search_google(
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


def get_private_key_from_gcp_secret(
    secret_id: str,
    project_id: str = "582587111398",  # Gnosis AI default project_id
    version_id: str = "latest",
) -> PrivateKey:
    # If credentials filename specified, use that, else read using default credentials path.
    google_application_credentials_filename = (
        CloudCredentials().google_application_credentials
    )
    if google_application_credentials_filename is not None:
        # mypy interprets incorrectly that from_service_account_json requires further args.
        client = secretmanager.SecretManagerServiceClient.from_service_account_json(filename=google_application_credentials_filename)  # type: ignore [call-arg]
    else:
        client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    secret_payload = response.payload.data.decode("UTF-8")
    secret_json = json.loads(secret_payload)
    if "private_key" not in secret_json:
        raise ValueError(f"Private key not found in gcp secret {secret_id}")
    return PrivateKey(SecretStr(secret_json["private_key"]))
