import atexit
import shlex
import socket
import subprocess
import sys
import time

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import HTTPProvider, Web3

from prediction_market_agent_tooling.loggers import logger

# Local chain setup for tests.
# Heavily inspired by Kartpatkey's Roles Royce (https://github.com/karpatkey/roles_royce/blob/main/tests/utils.py)


def get_anvil_test_accounts() -> list[LocalAccount]:
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
