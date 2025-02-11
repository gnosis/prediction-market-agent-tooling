from prediction_market_agent_tooling.gtypes import xdai_type, xDai, ChecksumAddress
from prediction_market_agent_tooling.tools.balances import get_balances
from web3 import Web3


def get_total_balance(
    address: ChecksumAddress,
    web3: Web3 | None = None,
    sum_xdai: bool = True,
    sum_wxdai: bool = True,
) -> xDai:
    """
    Checks if the total balance of xDai and wxDai in the wallet is above the minimum required balance.
    """
    current_balances = get_balances(address, web3)
    # xDai and wxDai have equal value and can be exchanged for almost no cost, so we can sum them up.
    total_balance = 0.0
    if sum_xdai:
        total_balance += current_balances.xdai
    if sum_wxdai:
        total_balance += current_balances.wxdai
    return xdai_type(total_balance)
