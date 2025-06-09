import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei, private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenThumbnailMapping,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)


def main(
    private_key: str,
    from_address: str,
    to_address: str,
) -> None:
    """
    Copy all existing image mapping on markets created by `private_key`, from OmenThumbnailMapping contract on `from_address` to OmenThumbnailMapping contract on `to_address`.
    """
    keys = APIKeys(BET_FROM_PRIVATE_KEY=private_key_type(private_key))

    markets = OmenSubgraphHandler().get_omen_markets(
        limit=None,
        creator=keys.bet_from_address,
        liquidity_bigger_than=Wei(0),
    )

    old_image_contract = OmenThumbnailMapping(
        address=Web3.to_checksum_address(from_address)
    )
    new_image_contract = OmenThumbnailMapping(
        address=Web3.to_checksum_address(to_address)
    )

    for market in markets:
        old_image = old_image_contract.get(
            market.market_maker_contract_address_checksummed
        )
        new_image = new_image_contract.get(
            market.market_maker_contract_address_checksummed
        )

        if new_image is None and old_image is not None:
            logger.info(
                f"Copying image mapping for market {market.market_maker_contract_address_checksummed} image {old_image} from {old_image_contract.address} to {new_image_contract.address}"
            )
            new_image_contract.set(
                keys, market.market_maker_contract_address_checksummed, old_image
            )


if __name__ == "__main__":
    typer.run(main)
