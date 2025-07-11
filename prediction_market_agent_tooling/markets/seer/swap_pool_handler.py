from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
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
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain


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
        amount_wei: Wei,
        token_in: ChecksumAddress,
        price_outcome_token: CollateralToken,
        buffer_pct: float = 0.05,
    ) -> Wei:
        is_buying_outcome = token_in == self.collateral_token_address

        if is_buying_outcome:
            value = amount_wei.value * (1.0 - buffer_pct) / price_outcome_token.value
        else:
            value = amount_wei.value * price_outcome_token.value * (1.0 - buffer_pct)
        return Wei(int(value))

    def buy_or_sell_outcome_token(
        self,
        amount_wei: Wei,
        token_in: ChecksumAddress,
        token_out: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """Buys/sells outcome_tokens in exchange for collateral tokens"""
        if self.collateral_token_address not in [token_in, token_out]:
            raise ValueError(
                f"trading outcome_token for a token different than collateral_token {self.collateral_token_address} is not supported. {token_in=} {token_out=}"
            )

        outcome_token = (
            token_in if token_in != self.collateral_token_address else token_out
        )

        # We could use a quoter contract (https://github.com/SwaprHQ/swapr-sdk/blob/develop/src/entities/trades/swapr-v3/constants.ts#L7), but since there is normally 1 pool per outcome token/collateral pair, it's not necessary.

        price_outcome_token = PriceManager.build(
            HexBytes(HexStr(self.market_id))
        ).get_token_price_from_pools(token=outcome_token)
        if not price_outcome_token:
            raise ValueError(
                f"Could not find price for {outcome_token=} and {self.collateral_token_address}"
            )

        amount_out_minimum = self._calculate_amount_out_minimum(
            amount_wei=amount_wei,
            token_in=token_in,
            price_outcome_token=price_outcome_token.priceOfCollateralInAskingToken,
        )

        p = ExactInputSingleParams(
            token_in=token_in,
            token_out=token_out,
            recipient=self.api_keys.bet_from_address,
            amount_in=amount_wei,
            amount_out_minimum=amount_out_minimum,
        )

        # make sure user has enough tokens to sell
        balance_collateral_token = ContractERC20OnGnosisChain(
            address=token_in
        ).balanceOf(self.api_keys.bet_from_address, web3=web3)
        if balance_collateral_token < amount_wei:
            raise ValueError(
                f"Balance {balance_collateral_token} of {token_in} insufficient for trade, required {amount_wei}"
            )

        tx_receipt = SwaprRouterContract().exact_input_single(
            api_keys=self.api_keys, params=p, web3=web3
        )
        return tx_receipt
