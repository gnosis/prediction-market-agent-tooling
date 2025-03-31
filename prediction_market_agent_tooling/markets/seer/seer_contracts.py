import os
import typing as t

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    OutcomeStr,
    TxReceipt,
    xDai,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractOnGnosisChain,
    abi_field_validator,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


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
        outcomes: t.Sequence[OutcomeStr],
        opening_time: DatetimeUTC,
        min_bond: xDai,
        language: str = "en_US",
        category: str = "misc",
    ) -> CreateCategoricalMarketsParams:
        return CreateCategoricalMarketsParams(
            market_name=market_question,
            token_names=[
                o.upper() for o in outcomes
            ],  # Following usual token names on Seer (YES,NO).
            min_bond=min_bond.as_xdai_wei.as_wei,
            opening_time=int(opening_time.timestamp()),
            outcomes=list(outcomes),
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
