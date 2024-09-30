import json
import tempfile

from pinatapy import PinataPy

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import IPFSCIDVersion0
from prediction_market_agent_tooling.markets.omen.data_models import IPFSAgentResult


class IPFSHandler:
    def __init__(self, api_keys: APIKeys):
        self.pinata = PinataPy(
            api_keys.pinata_api_key.get_secret_value(),
            api_keys.pinata_api_secret.get_secret_value(),
        )

    def upload_file(self, file_path: str) -> IPFSCIDVersion0:
        return IPFSCIDVersion0(
            self.pinata.pin_file_to_ipfs(file_path, save_absolute_paths=False)[
                "IpfsHash"
            ]
        )

    def store_agent_result(self, agent_result: IPFSAgentResult) -> IPFSCIDVersion0:
        with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as json_file:
            json.dump(agent_result.model_dump(), json_file, indent=4)
            json_file.flush()
            ipfs_hash = self.upload_file(json_file.name)
            return ipfs_hash

    def unpin_file(self, hash_to_remove: str) -> None:
        self.pinata.remove_pin_from_ipfs(hash_to_remove=hash_to_remove)
