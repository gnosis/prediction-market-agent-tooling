import json
import tempfile

import base58
import typer
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler


class Orga(BaseModel):
    name: str
    description: str


def build_digest_from_cid(cid: str) -> str:
    decoded: bytes = base58.b58decode(cid)
    digest = decoded[2:]  # remove multihash prefix (2 bytes)
    return "0x" + digest.hex()


def main(
    from_private_key: str = typer.Option(),
    organization_name: str = typer.Option(),
    organization_description: str = typer.Option(),
) -> None:
    """
    Helper script to create a market on Omen, usage:

    ```bash
    python scripts/store_prediction.py \
        --from-private-key your-private-key
        --organization_name my-organization

    ```
    """

    assert len(organization_name) < 32, "Organization name too long"

    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=None,
    )

    ipfs_handler = IPFSHandler(api_keys)
    agent_description = Orga(
        name=organization_name, description=organization_description
    )
    with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as json_file:
        json.dump(agent_description.model_dump(), json_file, indent=4)
        json_file.flush()
        ipfs_hash = ipfs_handler.upload_file(json_file.name)
    digest = build_digest_from_cid(ipfs_hash)
    print(f"{digest=} {ipfs_hash=} {organization_name=}")


if __name__ == "__main__":
    typer.run(main)
