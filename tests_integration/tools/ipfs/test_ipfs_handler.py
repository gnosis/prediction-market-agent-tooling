import datetime
from tempfile import TemporaryFile, NamedTemporaryFile

import pytest
import typing as t

import requests

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent import DeployableTraderAgent
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler


@pytest.fixture(scope="module")
def test_ipfs_handler() -> t.Generator[IPFSHandler,None,None]:
    keys = APIKeys()
    yield IPFSHandler(keys)

def test_ipfs_upload_and_removal(test_ipfs_handler: IPFSHandler):
    # We add the current datetime to avoid uploading an existing file (CID is content-based)
    temp_string = f"Hello World {datetime.datetime.utcnow()}"
    with NamedTemporaryFile() as temp_file:
        temp_file.write(temp_string.encode('utf-8'))
        temp_file.flush()
        ipfs_hash = test_ipfs_handler.upload_file(temp_file.name)

    # assert uploaded
    r = requests.get(f"https://ipfs.io/ipfs/{ipfs_hash}")
    r.raise_for_status()
    assert r.text == temp_string
    # remove from IPFS
    test_ipfs_handler.unpin_file(ipfs_hash)
