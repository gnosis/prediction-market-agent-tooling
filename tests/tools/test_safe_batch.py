from web3 import Web3

from prediction_market_agent_tooling.gtypes import ABI, Wei
from prediction_market_agent_tooling.tools.web3_utils import (
    SafeBatchCall,
    encode_contract_call,
)

ERC20_ABI: ABI = ABI(
    '[{"constant": false, "inputs": [{"name": "spender", "type": "address"}, '
    '{"name": "amount", "type": "uint256"}], "name": "approve", "outputs": '
    '[{"name": "", "type": "bool"}], "payable": false, "stateMutability": '
    '"nonpayable", "type": "function"}]'
)

TOKEN = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
SPENDER = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")


def test_encode_contract_call_produces_safe_batch_call() -> None:
    call = encode_contract_call(
        web3=Web3(),
        contract_address=TOKEN,
        contract_abi=ERC20_ABI,
        function_name="approve",
        function_params=[SPENDER, Wei(1_000_000)],
    )
    assert isinstance(call, SafeBatchCall)
    assert call.to == TOKEN
    assert call.value == 0
    # approve(address,uint256) selector is 0x095ea7b3
    hex_data = call.data.to_0x_hex()
    assert hex_data.startswith("0x095ea7b3")
    # spender address padded into the next 32 bytes
    assert SPENDER.lower().removeprefix("0x") in hex_data.lower()
    # amount 1_000_000 = 0xf4240
    assert hex_data.endswith("f4240")


def test_encode_contract_call_default_value_zero() -> None:
    call = encode_contract_call(
        web3=Web3(),
        contract_address=TOKEN,
        contract_abi=ERC20_ABI,
        function_name="approve",
        function_params=[SPENDER, Wei(0)],
    )
    assert call.value == 0
