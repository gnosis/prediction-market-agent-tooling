import typer
from web3 import Web3

from prediction_market_agent_tooling.monitor.nft_game.fetch_metrics import (
    fetch_nft_transfers,
    extract_messages_exchanged,
    extract_balances_per_block,
)


def main() -> None:
    NFT_CONTRACT = Web3.to_checksum_address(
        "0x0D7C0Bd4169D090038c6F41CFd066958fe7619D0"
    )
    w3 = Web3(Web3.HTTPProvider("https://remote-anvil-2.ai.gnosisdev.com"))
    fetch_nft_transfers(web3=w3, nft_contract_address=NFT_CONTRACT)
    extract_messages_exchanged()
    extract_balances_per_block()


if __name__ == "__main__":
    typer.run(main)
