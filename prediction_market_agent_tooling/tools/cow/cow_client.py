import httpx
from pyasn1.type.univ import Any

from prediction_market_agent_tooling.config import APIKeys


class ClientCoW:
    """
    TODO: This was a quick fix because we were already calling cow api manually.
    But ideally we should use https://github.com/cowdao-grants/cow-py.
    """

    def __init__(self) -> None:
        self.cow_api_key = APIKeys().COW_API_KEY

    @property
    def _url(self) -> str:
        if self.cow_api_key is None:
            return "https://api.cow.fi"

        else:
            return "https://partners.cow.fi"

    async def get_async(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        headers = (
            {"X-API-Key": self.cow_api_key.get_secret_value()}
            if self.cow_api_key
            else {}
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self._url + endpoint, params=params, headers=headers
            )
            response.raise_for_status()
            result: dict[str, Any] | list[dict[str, Any]] = response.json()
            return result

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        headers = (
            {"X-API-Key": self.cow_api_key.get_secret_value()}
            if self.cow_api_key
            else {}
        )

        with httpx.Client() as client:
            response = client.get(self._url + endpoint, params=params, headers=headers)
            response.raise_for_status()
            result: dict[str, Any] | list[dict[str, Any]] = response.json()
            return result
