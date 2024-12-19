import zlib

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.tools.contract import AgentCommunicationContract
from prediction_market_agent_tooling.tools.data_models import MessageContainer
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


def test_count_unseen_messages(local_web3: Web3) -> None:
    keys = APIKeys()
    mock_agent_address = keys.bet_from_address
    comm_contract = AgentCommunicationContract()

    initial_messages = comm_contract.count_unseen_messages(
        agent_address=mock_agent_address, web3=local_web3
    )
    assert initial_messages == 0  # no messages yet
    # add new message
    message = MessageContainer(
        sender=mock_agent_address,
        recipient=mock_agent_address,
        message=zlib.compress(b"Hello there!"),
    )

    comm_contract.send_message(
        api_keys=keys,
        agent_address=mock_agent_address,
        message=message,
        amount_wei=xdai_to_wei(xDai(0.1)),
        web3=local_web3,
    )
    assert (
        comm_contract.count_unseen_messages(
            agent_address=mock_agent_address, web3=local_web3
        )
        == 1
    )


def test_pop_message(local_web3: Web3) -> None:
    keys = APIKeys()
    mock_agent_address = keys.bet_from_address
    comm_contract = AgentCommunicationContract()

    initial_messages = comm_contract.count_unseen_messages(
        agent_address=mock_agent_address, web3=local_web3
    )
    assert initial_messages == 0  # no messages yet
    # add new message
    message = MessageContainer(
        sender=mock_agent_address,
        recipient=mock_agent_address,
        message=zlib.compress(b"Hello there!"),
    )

    comm_contract.send_message(
        api_keys=keys,
        agent_address=mock_agent_address,
        message=message,
        amount_wei=xdai_to_wei(xDai(0.1)),
        web3=local_web3,
    )
    assert (
        comm_contract.count_unseen_messages(
            agent_address=mock_agent_address, web3=local_web3
        )
        == 1
    )

    # fetch latest message
    stored_message = comm_contract.pop_message(
        keys, mock_agent_address, web3=local_web3
    )
    # assert message match
    assert message.message == stored_message.message
    assert message.recipient == stored_message.agent_address
