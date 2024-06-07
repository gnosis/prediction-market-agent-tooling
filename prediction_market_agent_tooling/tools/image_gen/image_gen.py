import base64
import io

from PIL import Image

from prediction_market_agent_tooling.config import APIKeys


def generate_image(
    prompt: str,
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
) -> Image:
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
    image = Image.open(io.BytesIO(base64.b64decode(response.b64_json)))
    return image
