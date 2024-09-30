import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    ContractPrediction,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def main(
    from_private_key: str = typer.Option(),
) -> None:
    """
    Helper script to create a market on Omen, usage:

    ```bash
    python scripts/store_prediction.py \
        --from-private-key your-private-key
    ```

    Market can be created also on the web: https://aiomen.eth.limo/#/create
    """

    agent_result_mapping = OmenAgentResultMappingContract()
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=None,
    )
    market_address = Web3.to_checksum_address(api_keys.public_key)
    dummy_transaction_hash = (
        "0x3750ffa211dab39b4d0711eb27b02b56a17fa9d257ee549baa3110725fd1d41b"
    )
    contract_prediction = ContractPrediction(
        tx_hashes=[HexBytes(dummy_transaction_hash)],
        estimated_probability_bps=5454,
        ipfs_hash=HexBytes(dummy_transaction_hash),
        publisher=api_keys.public_key,
    )
    tx_hash = agent_result_mapping.add_prediction(
        api_keys=api_keys, market_address=market_address, prediction=contract_prediction
    )

    logger.info(f"Added prediction, tx_hash {tx_hash}")


if __name__ == "__main__":
    typer.run(main)
