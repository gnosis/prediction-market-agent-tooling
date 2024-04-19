import atexit
import codecs
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time

import pytest
from eth_account import Account
from eth_account.signers.local import LocalAccount
from loguru import logger
from web3 import HTTPProvider, Web3
from web3.exceptions import ContractLogicError
from web3.types import TxReceipt

REMOTE_ETH_NODE_URL = codecs.decode(
    b"x\x9c\xcb())(\xb6\xd2\xd7O-\xc9\xd0\xcdM\xcc\xcc\xcbK-\xd1K\xd7K\xccI\xceH\xcd\xad\xd4K\xce\xcf\xd5/3\xd2\x0f"
    b"u)74-6NNu\xb3\xcc\x0f\nH\n\xcb\xccq4\xd4u\xcd3(53+\xf32\n(\x06\x00Q\x92\x17X",
    "zlib",
).decode()
REMOTE_GC_NODE_URL = "https://rpc.ankr.com/gnosis"

ETH_FORK_NODE_URL = os.environ.get("RR_ETH_FORK_URL", REMOTE_ETH_NODE_URL)
GC_FORK_NODE_URL = os.environ.get("RR_GC_FORK_URL", REMOTE_GC_NODE_URL)
ETH_LOCAL_NODE_PORT = 8546
GC_LOCAL_NODE_PORT = 8547
ETH_LOCAL_NODE_DEFAULT_BLOCK = 17565000
GC_LOCAL_NODE_DEFAULT_BLOCK = 30397769
RUN_LOCAL_NODE = os.environ.get("RR_RUN_LOCAL_NODE", False)
ETH_LOCAL_NODE_URL = f"http://127.0.0.1:{ETH_LOCAL_NODE_PORT}"
GC_LOCAL_NODE_URL = f"http://127.0.0.1:{GC_LOCAL_NODE_PORT}"
DIR_OF_THIS_FILE = os.path.dirname(os.path.abspath(__file__))


def get_anvil_test_accounts() -> list[LocalAccount]:
    # test accounts are generated using the mnemonic:
    #   "test test test test test test test test test test test junk" and derivation path "m/44'/60'/0'/0"
    keys = [
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
        "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
        "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
        "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
        "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
        "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
        "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
        "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
        "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
    ]
    return [Account.from_key(key) for key in keys]


TEST_ACCOUNTS = get_anvil_test_accounts()
SCRAPE_ACCOUNT = Account.from_key(
    "0xf214f2b2cd398c806f84e317254e0f0b801d0643303237d97a22a48e01628897"
)


@pytest.fixture(scope="module")
def web3_gnosis() -> Web3:
    return Web3(HTTPProvider("https://rpc.ankr.com/gnosis"))


@pytest.fixture(scope="module")
def web3_eth() -> Web3:
    return Web3(HTTPProvider(REMOTE_ETH_NODE_URL))


def wait_for_port(port, host="localhost", timeout=5.0):
    """Wait until a port starts accepting TCP connections."""
    start_time = time.time()
    while True:
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return
        except socket.error:
            time.sleep(0.05)
            if time.time() - start_time >= timeout:
                raise socket.error("Timeout waiting for port")


class SimpleDaemonRunner(object):
    def __init__(self, cmd, popen_kwargs=None):
        self.console = None
        self.proc = None
        self.cmd = cmd
        self.popen_kwargs = popen_kwargs or {}

    def start(self):
        if self.is_running():
            raise ValueError("Process is already running")
        logger.info("Starting daemon: %s %s", self.cmd, self.popen_kwargs)
        self.proc = subprocess.Popen(shlex.split(self.cmd), **self.popen_kwargs)
        atexit.register(self.stop)

    def stop(self):
        if not self.proc:
            return

        self.proc.terminate()
        stdout, stderr = self.proc.communicate(timeout=20)
        retcode = self.proc.returncode

        self.proc = None
        return retcode

    def is_running(self):
        return self.proc is not None


def fork_unlock_account(w3, address):
    """Unlock the given address on the forked node."""
    return w3.provider.make_request("anvil_impersonateAccount", [address])


def fork_reset_state(w3: Web3, url: str, block: int | str = "latest"):
    """Reset the state of the forked node to the state of the blockchain node at the given block.

    Args:
        w3: Web3 instance of the local node
        url: URL of the node from which to fork
        block: Block number at which to fork the blockchain, or "latest" to use the latest block
    """

    if isinstance(block, str):
        if block == "latest":
            raise ValueError("Can't use 'latest' as fork block")
    return w3.provider.make_request(
        "anvil_reset", [{"forking": {"jsonRpcUrl": url, "blockNumber": block}}]
    )


def mine_block(w3: Web3):
    logger.debug("mining block")
    return w3.provider.make_request("anvil_mine", [])


def run_hardhat():
    """Run hardhat node in the background."""
    try:
        npm = shutil.which("npm")
        subprocess.check_call([npm, "--version"])
        if "hardhat" not in json.loads(
            subprocess.check_output([npm, "list", "--json"])
        ).get("dependencies", {}):
            raise subprocess.CalledProcessError
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "Hardhat is not installed properly. Check the README for instructions."
        )

    log_filename = "/tmp/rr_hardhat_log.txt"
    logger.info(f"Writing Hardhat log to {log_filename}")
    hardhat_log = open(log_filename, "w")
    npx = shutil.which("npx")
    node = SimpleDaemonRunner(
        cmd=f"{npx} hardhat node --show-stack-traces --fork '{ETH_FORK_NODE_URL}' --fork-block-number {ETH_LOCAL_NODE_DEFAULT_BLOCK} --port {ETH_LOCAL_NODE_PORT}",
        popen_kwargs={"stdout": hardhat_log, "stderr": hardhat_log},
    )
    node.start()
    return node


def run_anvil(url: str, block: int | None, port: int = 8545):
    """Run anvil node in the background"""
    cmd = f"anvil --accounts 10 -f '{url}' --port {port}"
    if block:
        cmd += f" --fork-block-number {block}"
    node = SimpleDaemonRunner(
        cmd=cmd,
        popen_kwargs={"stdout": sys.stdout, "stderr": sys.stderr},
    )

    node.start()
    return node


class LocalNode:
    def __init__(
        self, remote_url: str, port: int = 8545, default_block: int | None = None
    ):
        self.remote_url = remote_url
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.default_block = default_block
        self.w3 = Web3(HTTPProvider(self.url, request_kwargs={"timeout": 30}))

    def reset_state(self):
        fork_reset_state(self.w3, self.remote_url, self.default_block)

    def unlock_account(self, address: str):
        fork_unlock_account(self.w3, address)

    def set_block(self, block):
        """Set the local node to a specific block"""
        fork_reset_state(self.w3, url=self.remote_url, block=block)


def _local_node(
    node: LocalNode, start_local_node: bool = True
) -> SimpleDaemonRunner | None:
    """Run a local node_daemon for testing"""
    node_daemon = None
    if start_local_node:
        node_daemon = run_anvil(node.remote_url, node.default_block, node.port)

    wait_for_port(node.port, timeout=20)
    return node_daemon

    class LatencyMeasurerMiddleware:
        def __init__(self, make_request, w3):
            self.w3 = w3
            self.make_request = make_request

        def __call__(self, method, params):
            import time

            start_time = time.monotonic()
            response = self.make_request(method, params)
            logger.debug(
                "Web3 time spent in %s: %f seconds",
                method,
                time.monotonic() - start_time,
            )
            return response

    node.w3.middleware_onion.add(LatencyMeasurerMiddleware, "latency_middleware")
    node.reset_state()
    return node


def top_up_address(w3: Web3, address: str, amount: int) -> None:
    """Top up an address with ETH"""
    if amount > (w3.eth.get_balance(SCRAPE_ACCOUNT.address) * 1e18) * 0.99:
        raise ValueError("Not enough ETH in the faucet account")
    try:
        w3.eth.send_transaction(
            {
                "to": address,
                "value": Web3.to_wei(amount, "ether"),
                "from": SCRAPE_ACCOUNT.address,
            }
        )
    except ContractLogicError:
        raise Exception("Address is a smart contract address with no payable function.")


def to_hex_32_bytes(value: str | int) -> str:
    """Convert a value to a 32 bytes hex string"""
    if isinstance(value, str):
        if value.startswith("0x") and len(value) <= 66:
            return "0x" + value[2:].rjust(64, "0")
        else:
            raise ValueError(
                "Invalid value. Value must be a hex string with or without 0x prefix and length <= 66"
            )
    elif isinstance(value, int):
        return Web3.to_hex(Web3.to_bytes(value).rjust(32, b"\0"))
    else:
        raise ValueError(
            "Invalid value. Value must be an int or a hex string with 0x prefix and length <= 66"
        )


def assign_role(
    local_node,
    avatar_safe_address: str,
    roles_mod_address: str,
    role: int,
    asignee: str,
) -> TxReceipt:
    asignee_32_bytes = to_hex_32_bytes(asignee)
    role_32_byes = to_hex_32_bytes(role)
    a = asignee_32_bytes[2:]
    calldata_to_assign_role = (
        f"0xa6edf38f"
        f"{asignee_32_bytes[2:]}"
        f"0000000000000000000000000000000000000000000000000000000000000060"
        f"00000000000000000000000000000000000000000000000000000000000000a0"
        f"0000000000000000000000000000000000000000000000000000000000000001"
        f"{role_32_byes[2:]}"
        f"0000000000000000000000000000000000000000000000000000000000000001"
        f"0000000000000000000000000000000000000000000000000000000000000001"
    )

    tx_to_assign_role = {
        "from": avatar_safe_address,
        "to": roles_mod_address,
        "data": calldata_to_assign_role,
        "value": "0",
    }

    local_node.unlock_account(avatar_safe_address)
    # The amount of ETH of the Avatar address is increased
    top_up_address(local_node.w3, address=avatar_safe_address, amount=1)
    tx_hash = local_node.w3.eth.send_transaction(tx_to_assign_role)
    tx_receipt = local_node.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=5)
    return tx_receipt
