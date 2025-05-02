from pathlib import Path

from pydantic import SecretStr
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ABI, PrivateKey
from prediction_market_agent_tooling.tools.web3_utils import (
    send_function_on_contract_tx,
)


def read_abi(abi_path: Path) -> ABI:
    with open(abi_path, "r") as f:
        return ABI(f.read())


if __name__ == "__main__":
    w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))

    hub_abi_path = Path("prediction_market_agent_tooling/abis/hub.abi.json")
    erc20lift_abi_path = Path("prediction_market_agent_tooling/abis/erc20lift.abi.json")

    hub_abi = read_abi(hub_abi_path)
    erc20lift_abi = read_abi(erc20lift_abi_path)
    from_private_key = (
        "0x8ce3077e3330df6eafb6f0f941f4a6d4b47a3719e564d8dce602d03355acb65e"  # metri
    )
    group_address = Web3.to_checksum_address(
        "0xc3d79a0d96c643568e085d667e79a61a6da061c8"
    )
    hub_address = Web3.to_checksum_address("0xc12C1E50ABB450d6205Ea2C3Fa861b3B834d13e8")
    erc20lift_address = Web3.to_checksum_address(
        "0x5f99a795dd2743c36d63511f0d4bc667e6d3cdb5"
    )
    tx = send_function_on_contract_tx(
        web3=w3,
        contract_address=hub_address,
        contract_abi=hub_abi,
        from_private_key=PrivateKey(SecretStr(from_private_key)),  # from_private_key,
        function_name="wrap",
        function_params=[
            group_address,
            0,
            1,
        ],
    )
    print(f"wrap {tx=}")
    erc20_lift_contract = w3.eth.contract(address=erc20lift_address, abi=erc20lift_abi)
    circles_type = 1

    erc20address = erc20_lift_contract.functions["erc20Circles"](
        circles_type, group_address
    ).call()
    print(f"{erc20address=}")

    # ToDo - Create market with that token as collateral

    print("end")
