from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    WRAPPED_XDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20OnGnosisChain,
)

# This is the token where agents will hold their funds,
# except for a small portion that will be kept in the native token of the network to pay for the fees.
# Auto deposit must work from native token into this token.
# If changed, then keep in mind that we assume this token is equal to 1 USD.
# Also if changed, `send_keeping_token_to_eoa_xdai` will require update.
KEEPING_ERC20_TOKEN = ContractDepositableWrapperERC20OnGnosisChain(
    address=WRAPPED_XDAI_CONTRACT_ADDRESS
)

MINIMUM_NATIVE_TOKEN_IN_EOA_FOR_FEES = xdai_type(0.1)
