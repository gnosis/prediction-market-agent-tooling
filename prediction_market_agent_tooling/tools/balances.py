from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import ChecksumAddress, xDai
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.tools.gnosis_rpc import get_balance
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai


class Balances(BaseModel):
    xdai: xDai
    wxdai: xDai


def get_balances(address: ChecksumAddress) -> Balances:
    xdai = wei_to_xdai(get_balance(address))
    wxdai = wei_to_xdai(WrappedxDaiContract().balanceOf(address))
    return Balances(xdai=xdai, wxdai=wxdai)
