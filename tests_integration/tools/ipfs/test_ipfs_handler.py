import datetime
import typing as t
from tempfile import NamedTemporaryFile

import pytest
import requests

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler


@pytest.fixture(scope="module")
def test_ipfs_handler() -> t.Generator[IPFSHandler, None, None]:
    keys = APIKeys()
    yield IPFSHandler(keys)


def test_ipfs_upload_and_removal(test_ipfs_handler: IPFSHandler) -> None:
    # We add the current datetime to avoid uploading an existing file (CID is content-based)
    temp_string = f"Hello World {datetime.datetime.utcnow()}"
    with NamedTemporaryFile() as temp_file:
        temp_file.write(temp_string.encode("utf-8"))
        temp_file.flush()
        ipfs_hash = test_ipfs_handler.upload_file(temp_file.name)

    # assert uploaded
    # can take a while to be available for download
    # r = requests.get(f"https://ipfs.io/ipfs/{ipfs_hash}", timeout=120)
    r = requests.get(f"https://gateway.pinata.cloud/ipfs/{ipfs_hash}", timeout=60)
    r.raise_for_status()
    assert r.text == temp_string
    # remove from IPFS
    test_ipfs_handler.unpin_file(ipfs_hash)
