from pydantic import BaseModel
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.gtypes import ChecksumAddress, xDai
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai


class Balances(BaseModel):
    xdai: xDai
    wxdai: xDai

    @property
    def total(self) -> xDai:
        return self.xdai + self.wxdai


def get_balances(address: ChecksumAddress, web3: Web3 | None = None) -> Balances:
    if not web3:
        web3 = WrappedxDaiContract().get_web3()
    xdai_balance = Wei(web3.eth.get_balance(address))
    xdai = wei_to_xdai(xdai_balance)
    wxdai = wei_to_xdai(WrappedxDaiContract().balanceOf(address, web3=web3))
    return Balances(xdai=xdai, wxdai=wxdai)
