from typing import List, Optional
from eth_typing import ChecksumAddress
from web3.types import Nonce, TxParams, TxReceipt, Wei
from web3 import Web3
from gnosis.eth import EthereumClient, EthereumTxSent
from gnosis.eth.constants import NULL_ADDRESS
from gnosis.eth.contracts import get_safe_V1_3_0_contract
from gnosis.safe import ProxyFactory, Safe

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes

def _deploy_test_safe(
        self,
        initializer: bytes,
        master_copy_address: ChecksumAddress,
        initial_funding_wei: Optional[Wei] = None,
    ) -> Safe:
        """
        Internal method to deploy a Safe given the initializer and master copy

        :param initializer:
        :param master_copy_address:
        :param initial_funding_wei: If provided, funds will be sent to the Safe
        :return: A deployed Safe
        """
        ethereum_tx_sent = self.proxy_factory.deploy_proxy_contract_with_nonce(
            self.ethereum_test_account,
            master_copy_address,
            initializer=initializer,
        )
        safe = Safe(
            ethereum_tx_sent.contract_address,
            self.ethereum_client,
            simulate_tx_accessor_address=self.simulate_tx_accessor_V1_4_1.address,
        )

        if initial_funding_wei:
            self.send_ether(safe.address, initial_funding_wei)

        return safe

def _deploy_new_test_safe(
        master_copy_version: str,
        master_copy_address: ChecksumAddress,
        number_owners: int = 3,
        threshold: Optional[int] = None,
        owners: Optional[List[ChecksumAddress]] = None,
        initial_funding_wei: int = 0,
        fallback_handler: Optional[ChecksumAddress] = None,
    ) -> Safe:
        """
        Internal method to deploy Safes from 1.1.1 to 1.4.1, as setup method didn't change

        :param master_copy_version:
        :param master_copy_address:
        :param number_owners:
        :param threshold:
        :param owners:
        :param initial_funding_wei:
        :param fallback_handler:
        :return: A deployed Safe
        """

        fallback_handler = (
            fallback_handler or self.compatibility_fallback_handler.address
        )
        owners = (
            owners
            if owners
            else [Account.create().address for _ in range(number_owners)]
        )
        if not threshold:
            threshold = len(owners) - 1 if len(owners) > 1 else 1
        to = NULL_ADDRESS
        data = b""
        payment_token = NULL_ADDRESS
        payment = 0
        payment_receiver = NULL_ADDRESS
        initializer = HexBytes(
            self.safe_contract_V1_4_1.functions.setup(
                owners,
                threshold,
                to,
                data,
                fallback_handler,
                payment_token,
                payment,
                payment_receiver,
            ).build_transaction(get_empty_tx_params())["data"]
        )

        safe = self._deploy_test_safe(
            initializer, master_copy_address, initial_funding_wei=initial_funding_wei
        )


def main():

    print ('start') 
    

    # addresses.MASTER_COPIES[EthereumNetwork.MAINNET]
    MASTER_COPY_141 = "0x41675C099F32341bf84BFc5382aF534df5C7461a"
    CHAIN_RPC_URL = 'https://rpc.tenderly.co/fork/afb295ce-87ed-4bad-a38f-f7e3b32d2932'
    PROXY_FACTORY_ADDRESS = '0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67'
    web3 = Web3(Web3.HTTPProvider(CHAIN_RPC_URL))

    _deploy_new_test_safe(
            "1.4.1",
            MASTER_COPY_141,
            number_owners=1,
            threshold=1,
            owners=[Web3.to_checksum_address("0xC073C043189b79b18508cA9330f49B007D345605")],
            initial_funding_wei=0,
            fallback_handler=None,
        )



    print ('end')

if __name__ == "__main__":
    main()