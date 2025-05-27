import os
import typing as t

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    OutcomeStr,
    TxReceipt,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.seer.data_models import (
    ExactInputSingleParams,
    RedeemParams,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
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
            min_bond=min_bond.as_xdai_wei.value,
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


class GnosisRouter(ContractOnGnosisChain):
    # https://gnosisscan.io/address/0x83183da839ce8228e31ae41222ead9edbb5cdcf1#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/seer_gnosis_router.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xeC9048b59b3467415b1a38F63416407eA0c70fB8"
    )

    def redeem_to_base(
        self,
        api_keys: APIKeys,
        params: RedeemParams,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        params_dict = params.model_dump(by_alias=True)
        # We explicity set amounts since OutcomeWei gets serialized as dict
        params_dict["amounts"] = [amount.value for amount in params.amounts]
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="redeemToBase",
            function_params=params_dict,
            web3=web3,
        )
        return receipt_tx


class SwaprRouterContract(ContractOnGnosisChain):
    # File content taken from https://github.com/protofire/omen-exchange/blob/master/app/src/abi/marketMaker.json.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/swapr_router.abi.json",
        )
    )

    address: ChecksumAddress = Web3.to_checksum_address(
        "0xffb643e73f280b97809a8b41f7232ab401a04ee1"
    )

    def exact_input_single(
        self,
        api_keys: APIKeys,
        params: ExactInputSingleParams,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        # ToDo - check allowance
        erc20_token = ContractERC20OnGnosisChain(
            address=Web3.to_checksum_address(params.token_in)
        )

        if erc20_token.allowance(
            api_keys.bet_from_address, self.address, web3=web3
        ) < Wei(params.amount_in):
            erc20_token.approve(
                api_keys, self.address, Wei(params.amount_in), web3=web3
            )

        return self.send(
            api_keys=api_keys,
            function_name="exactInputSingle",
            function_params=[tuple(params.model_dump(by_alias=True).values())],
            web3=web3,
        )
