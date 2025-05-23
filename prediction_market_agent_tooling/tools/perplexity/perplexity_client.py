from typing import Any, Dict, List, Optional

import httpx
from pydantic import SecretStr

from prediction_market_agent_tooling.tools.perplexity.perplexity_models import (
    PerplexityModelSettings,
    PerplexityRequestParameters,
    PerplexityResponse,
)


class PerplexityModel:
    def __init__(
        self,
        model_name: str,
        *,
        api_key: SecretStr,
        completition_endpoint: str = "https://api.perplexity.ai/chat/completions",
    ) -> None:
        self.model_name: str = model_name
        self.api_key: SecretStr = api_key
        self.completition_endpoint: str = completition_endpoint

    async def request(
        self,
        messages: List[dict[str, str]],
        model_settings: Optional[PerplexityModelSettings],
        model_request_parameters: PerplexityRequestParameters,
    ) -> PerplexityResponse:
        payload: Dict[str, Any] = {"model": self.model_name, "messages": messages}

        if model_settings:
            model_settings_dict = model_settings.model_dump()
            model_settings_dict = {
                k: v for k, v in model_settings_dict.items() if v is not None
            }
            payload.update(model_settings_dict)

        params_dict = model_request_parameters.model_dump()
        params_dict = {k: v for k, v in params_dict.items() if v is not None}

        # Extract and handle search_context_size specially
        if "search_context_size" in params_dict:
            search_context_size = params_dict.pop("search_context_size")
            payload["web_search_options"] = {"search_context_size": search_context_size}

        # Add remaining Perplexity parameters to payload
        payload.update(params_dict)

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    self.completition_endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()

                choices = result.get("choices", [])
                if not choices:
                    raise ValueError("Invalid response: no choices")

                content = choices[0].get("message", {}).get("content")
                if not content:
                    raise ValueError("Invalid response: no content")

                return PerplexityResponse(
                    content=content,
                    citations=result.get("citations", []),
                    usage=result.get("usage", {}),
                )
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"HTTP error from Perplexity API: {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ValueError(f"Request error to Perplexity API: {str(e)}") from e
        except Exception as e:
            raise ValueError(
                f"Unexpected error in Perplexity API request: {str(e)}"
            ) from e
