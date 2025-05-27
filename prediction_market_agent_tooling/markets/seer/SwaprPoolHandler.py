from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexBytes,
    HexStr,
    TxReceipt,
    Wei,
)
from prediction_market_agent_tooling.markets.seer.data_models import (
    ExactInputSingleParams,
)
from prediction_market_agent_tooling.markets.seer.price_manager import PriceManager
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SwaprRouterContract,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


class SwaprPoolHandler:
    def __init__(
        self,
        api_keys: APIKeys,
        market: SeerAgentMarket,
        seer_subgraph: SeerSubgraphHandler | None = None,
    ):
        self.api_keys = api_keys
        self.seer_subgraph = seer_subgraph or SeerSubgraphHandler()
        self.market = market

    def swap(
        self,
        amount_wei: Wei,
        token_in: ChecksumAddress,
        token_out: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        subgraph = SeerSubgraphHandler()
        pool = subgraph.get_pool_by_token(
            token_address=token_in,
            collateral_address=self.market.collateral_token_contract_address_checksummed,
        )
        if not pool:
            raise ValueError(
                f"Could not find a pool for {token_in} and {self.market.collateral_token_contract_address_checksummed}"
            )
        # approximate out price getting the current price and adding a 10% buffer
        price_outcome_token = PriceManager.build(
            HexBytes(HexStr(self.market.id))
        ).get_price_for_token(token=token_in)
        amount_out_minimum = (
            amount_wei.value * 0.95 / price_outcome_token.value
            if price_outcome_token
            else 0.0
        )

        p = ExactInputSingleParams(
            token_in=token_in,
            token_out=token_out,
            recipient=self.api_keys.bet_from_address,
            amount_in=amount_wei.value,
            amount_out_minimum=int(amount_out_minimum),
        )

        tx_receipt = SwaprRouterContract().exact_input_single(
            api_keys=self.api_keys, params=p, web3=web3
        )
        return tx_receipt
