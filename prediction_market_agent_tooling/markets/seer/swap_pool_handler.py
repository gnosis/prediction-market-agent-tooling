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
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SwaprRouterContract,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


class SwapPoolHandler:
    def __init__(
        self,
        api_keys: APIKeys,
        market_id: str,
        collateral_token_address: ChecksumAddress,
        seer_subgraph: SeerSubgraphHandler | None = None,
    ):
        self.api_keys = api_keys
        self.market_id = market_id
        self.collateral_token_address = collateral_token_address
        self.seer_subgraph = seer_subgraph or SeerSubgraphHandler()

    def _calculate_amount_out_minimum(
        self,
        amount_in: Wei,
        token_in: ChecksumAddress,
        token_out: ChecksumAddress,
        buffer_pct: float = 0.05,
    ) -> Wei:
        price_manager = PriceManager.build(HexBytes(HexStr(self.market_id)))
        value = price_manager.get_swapr_input_quote(
            input_amount=amount_in, input_token=token_in, output_token=token_out
        )
        return value * (1 - buffer_pct)

    def buy_or_sell_outcome_token(
        self,
        amount_in: Wei,
        token_in: ChecksumAddress,
        token_out: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """Buys/sells outcome_tokens in exchange for collateral tokens"""
        if self.collateral_token_address not in [token_in, token_out]:
            raise ValueError(
                f"trading outcome_token for a token different than collateral_token {self.collateral_token_address} is not supported. {token_in=} {token_out=}"
            )

        amount_out_minimum = self._calculate_amount_out_minimum(
            amount_in=amount_in,
            token_in=token_in,
            token_out=token_out,
        )

        p = ExactInputSingleParams(
            token_in=token_in,
            token_out=token_out,
            recipient=self.api_keys.bet_from_address,
            amount_in=amount_in,
            amount_out_minimum=amount_out_minimum,
        )

        tx_receipt = SwaprRouterContract().exact_input_single(
            api_keys=self.api_keys, params=p, web3=web3
        )

        return tx_receipt
