from eth_account import Account
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from web3 import Web3

from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.tools.safe import create_safe


def main():
    print("start")
    # deploy safe

    # Fund safe
    private_key_anvil1 = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    private_key_anvil2 = (
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    )
    private_key_anvil3 = (
        "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
    )
    client = EthereumClient()
    account = Account.from_key(private_key_anvil1)
    account2 = Account.from_key(private_key_anvil2)
    account3 = Account.from_key(private_key_anvil3)

    # s = SafeManager(client, account, None)
    owners = [Web3.to_checksum_address(account.address), account2.address]
    safe_contract_address = create_safe(client, account, owners, 1)
    # safe_contract_address = Web3.to_checksum_address(
    #    "0x8DD8266809FC30DC008725653E87E4676840C4AE"
    # )

    wxdai = WrappedxDaiContract()
    wxdai_contract = client.w3.eth.contract(address=wxdai.address, abi=wxdai.abi)
    approve_quantity_wei = Web3.to_wei(100, "ether")
    tx_params = wxdai_contract.functions.approve(
        account2.address, approve_quantity_wei
    ).build_transaction(
        {
            "from": safe_contract_address,
            "nonce": client.w3.eth.get_transaction_count(safe_contract_address),
            "gas": 700000,
        }
    )
    # sign
    s = Safe(safe_contract_address, client)
    safe_tx = s.build_multisig_tx(to=tx_params["to"], data=tx_params["data"], value=0)
    safe_tx.sign(account.key.hex())
    safe_tx.call()
    safe_tx.execute(account.key.hex())
    # get allowance
    allowance = wxdai_contract.functions.allowance(
        safe_contract_address,
        account2.address,
    ).call()
    print(f"allowance {allowance}")
    assert allowance == approve_quantity_wei

    print("end")
    # m = s.deploy_safe(client, account, account, owners, 1)
    # already deployed
    # print(f"deployed safe {m.safe.address}")
    # sys.exit(1)
    # safe = Safe(
    #    Web3.to_checksum_address("0xE1f1538ABa3d76Ae934D8945D47705d322087c73"), client
    # )
    #  send from safe to account2 (should fail)
    #  approve account2 to spend wxDAI on behalf of safe
    #  send from safe to account2 using account2 as signer
    print("end")


if __name__ == "__main__":
    main()
