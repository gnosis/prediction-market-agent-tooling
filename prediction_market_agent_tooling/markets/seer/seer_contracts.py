import os

from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.seer.data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.tools.contract import (
    abi_field_validator,
    ContractOnGnosisChain,
)


class SeerRealitioContract(OmenRealitioContract):
    # ToDo - Write tests to make sure that same functionality is supported.
    # askNewQuestion is the same
    # Contract ABI taken from https://gnosisscan.io/address/0xe78996a233895be74a66f451f1019ca9734205cc#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/seer_realitio_3_0.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xe78996a233895be74a66f451f1019ca9734205cc"
    )


class Wrapped1155Factory(ContractOnGnosisChain):
    # ToDo - new functions
    # Contract ABI taken from https://gnosisscan.io/address/0xd194319d1804c1051dd21ba1dc931ca72410b79f#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/seer_wrapper_1155_factory.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xd194319d1804c1051dd21ba1dc931ca72410b79f"
    )


class MarketFactory(ContractOnGnosisChain):
    # ToDo - new functions
    # https://gnosisscan.io/address/0x83183da839ce8228e31ae41222ead9edbb5cdcf1#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/seer_market_factory.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x83183da839ce8228e31ae41222ead9edbb5cdcf1"
    )

    def market_count(self, web3: Web3 | None = None) -> int:
        count: int = self.call("marketCount", web3=web3)
        return count

    def create_categorical_market(
        self,
        api_keys: APIKeys,
        params: CreateCategoricalMarketsParams,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="createCategoricalMarket",
            function_params=[params.model_dump(by_alias=True)],
            web3=web3,
        )
        return receipt_tx

        # ToDo - Also return event NewMarket, emitted by this contract
