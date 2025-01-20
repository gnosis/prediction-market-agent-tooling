import time

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.monitor.nft_game.models import (
    AgentCommunicationMessage,
    ERC721Transfer,
    BalanceData,
)
from prediction_market_agent_tooling.tools.contract import (
    AgentCommunicationContract,
    ContractOwnableERC721BaseClass,
)
from prediction_market_agent_tooling.tools.parallelism import par_map


def fetch_nft_transfers(
    web3: Web3,
    nft_contract_address: ChecksumAddress,
    from_block: int = 37341108,
    to_block: int | None = None,
) -> list[ERC721Transfer]:
    s = ContractOwnableERC721BaseClass(address=nft_contract_address)
    nft_c = s.get_web3_contract(web3=web3)

    # fetch transfer events in the last block
    start = time.time()
    logs = nft_c.events.Transfer().get_logs(fromBlock=from_block, toBlock=to_block)
    logger.debug(f"elapsed {time.time() - start}")
    logger.debug(f"fetched {len(logs)} NFT transfers")
    events = [ERC721Transfer.from_event_log(log) for log in logs]
    return events


def extract_messages_exchanged(
    web3: Web3,
    from_block: int = 37341108,
    to_block: int | None = None,
) -> list[AgentCommunicationMessage]:
    agent_communication_contract = AgentCommunicationContract()
    agent_communication_c = agent_communication_contract.get_web3_contract(web3=web3)

    start = time.time()
    logs = agent_communication_c.events.LogMessage().get_logs(
        fromBlock=from_block, toBlock=to_block
    )
    logger.debug(f"elapsed {time.time() - start}")
    logger.debug(f"fetched {len(logs)} events from AgentCommunication contract")
    messages = [AgentCommunicationMessage.from_event_log(log) for log in logs]
    return messages


def get_balance_at_block(
    web3: Web3, address: ChecksumAddress, block: int | None = None
) -> tuple[Wei, int]:
    xdai_balance = Wei(web3.eth.get_balance(account=address, block_identifier=block))
    return xdai_balance, block


def extract_balances_per_block(
    web3: Web3,
    from_block: int = 37341108,
    to_block: int | None = None,
) -> list[AgentCommunicationMessage]:
    # ToDo - call get_balance in range(from_block, to_block + 1)
    blocks = list(range(from_block, to_block + 1))  # include end block

    NFT_agent_addresses = [
        "0xd845A24014B3BD96212A21f602a4F16A7dA518A4",
        "0xb4D8C8BedE2E49b08d2A22485f72fA516116FE7F",
        "0xC09a8aB38A554022ACBACBA174F14C8B35E89946",
        "0xd4fC4305DC1226c38356024c26cdE985817f137F",
        "0x84690A78d74e90608fc3e73cA79A06ee4F261A06",
        "0x64D94C8621128E1C813F8AdcD62c4ED7F89B1Fd6",
        "0x469Bc26531800068f306D304Ced56641F63ae140",
    ]
    NFT_agent_addresses = [Web3.to_checksum_address(i) for i in NFT_agent_addresses]

    balance_data: dict[ChecksumAddress, list[BalanceData]] = {}

    for address in NFT_agent_addresses:
        balances = par_map(
            items=blocks,
            func=lambda block: get_balance_at_block(
                web3=web3, address=address, block=block
            ),
        )
        balance_data[address] = [
            BalanceData(address=address, block=b, balance=balance)
            for balance, b in balances
        ]
    print(balance_data)
