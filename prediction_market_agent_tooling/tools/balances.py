from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress, Token, xDai, xDaiWei
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    sDaiContract,
)


class Balances(BaseModel):
    xdai: xDai
    wxdai: Token
    sdai: Token

    @property
    def total(self) -> Token:
        return self.xdai.as_token + self.wxdai + self.sdai


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def get_balances(address: ChecksumAddress, web3: Web3 | None = None) -> Balances:
    if not web3:
        web3 = WrappedxDaiContract().get_web3()
    xdai_balance = xDaiWei(web3.eth.get_balance(address))
    xdai = xdai_balance.as_xdai
    wxdai = WrappedxDaiContract().balanceOf(address, web3=web3).as_token
    sdai = sDaiContract().balanceOf(address, web3=web3).as_token
    return Balances(xdai=xdai, wxdai=wxdai, sdai=sdai)
