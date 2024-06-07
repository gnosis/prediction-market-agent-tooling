import base64
import io
import typing as t

from PIL import Image
from PIL.Image import Image as ImageType

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.utils import check_not_none


def generate_image(
    prompt: str,
    model: str = "dall-e-3",
    size: t.Literal[
        "256x256", "512x512", "1024x1024", "1792x1024", "1024x1792"
    ] = "1024x1024",
    quality: t.Literal["standard", "hd"] = "standard",
) -> ImageType:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai not installed, please install extras `openai` to use this function."
        )
    response = (
        OpenAI(
            api_key=APIKeys().openai_api_key.get_secret_value(),
        )
        .images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            response_format="b64_json",
            n=1,
        )
        .data[0]
    )
    image = Image.open(
        io.BytesIO(
            base64.b64decode(
                check_not_none(
                    response.b64_json, "Can't be none if response_format is b64_json."
                )
            )
        )
    )
    return image
