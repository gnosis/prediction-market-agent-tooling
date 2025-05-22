import os
from typing import Any, Dict, List, Optional

import httpx

from .perplexity_models import (
    PerplexityModelSettings,
    PerplexityRequestParameters,
    PerplexityResponse,
)


class PerplexityModel:
    def __init__(
        self,
        model_name: str,
        *,
        api_key: Optional[str] = None,
        completition_endpoint: str = "https://api.perplexity.ai/chat/completions",
    ) -> None:
        self.model_name: str = model_name
        self.api_key: str | None = api_key or os.environ.get("PERPLEXITY_API_KEY")
        self.completition_endpoint: str = completition_endpoint
        if not self.api_key:
            raise ValueError(
                "API key required. Set PERPLEXITY_API_KEY or pass api_key parameter."
            )

    async def request(
        self,
        messages: List[dict[str, str]],
        model_settings: Optional[PerplexityModelSettings],
        model_request_parameters: PerplexityRequestParameters,
    ) -> PerplexityResponse:
        # Start with base payload
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
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()

                return PerplexityResponse(
                    content=result["choices"][0]["message"]["content"],
                    citations=result["citations"],
                    usage=result.get("usage", {}),
                )
        except Exception as e:
            raise e
