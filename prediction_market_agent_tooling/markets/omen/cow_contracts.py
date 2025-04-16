import os

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ABI, HexBytes
from prediction_market_agent_tooling.tools.contract import (
    ContractOnGnosisChain,
    abi_field_validator,
)


class CowGPv2SettlementContract(ContractOnGnosisChain):
    # Contract ABI taken from https://github.com/cowprotocol/cow-sdk/blob/main/abi/GPv2Settlement.json.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/gvp2_settlement.abi.json",
        )
    )

    def setPreSignature(
        self,
        api_keys: APIKeys,
        orderId: HexBytes,
        signed: bool,
        web3: Web3 | None = None,
    ) -> None:
        self.send(
            api_keys=api_keys,
            function_name="setPreSignature",
            function_params=[orderId, signed],
            web3=web3,
        )
