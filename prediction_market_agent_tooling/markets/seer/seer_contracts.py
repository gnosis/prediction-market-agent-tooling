import os

from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ABI, ChecksumAddress, xDai
from prediction_market_agent_tooling.markets.seer.data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractOnGnosisChain,
    abi_field_validator,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


class SeerMarketFactory(ContractOnGnosisChain):
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

    @staticmethod
    def build_market_params(
        market_question: str,
        outcomes: list[str],
        opening_time: DatetimeUTC,
        min_bond_xdai: xDai,
        language: str = "en_US",
        category: str = "misc",
    ) -> CreateCategoricalMarketsParams:
        return CreateCategoricalMarketsParams(
            market_name=market_question,
            token_names=[
                o.upper() for o in outcomes
            ],  # Following usual token names on Seer (YES,NO).
            min_bond=xdai_to_wei(min_bond_xdai),
            opening_time=int(opening_time.timestamp()),
            outcomes=outcomes,
            lang=language,
            category=category,
        )

    def market_count(self, web3: Web3 | None = None) -> int:
        count: int = self.call("marketCount", web3=web3)
        return count

    def market_at_index(self, index: int, web3: Web3 | None = None) -> ChecksumAddress:
        market_address: str = self.call("markets", function_params=[index], web3=web3)
        return Web3.to_checksum_address(market_address)

    def collateral_token(self, web3: Web3 | None = None) -> ChecksumAddress:
        collateral_token_address: str = self.call("collateralToken", web3=web3)
        return Web3.to_checksum_address(collateral_token_address)

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
