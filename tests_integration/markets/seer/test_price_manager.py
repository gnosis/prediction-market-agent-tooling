# from eth_typing import HexStr
# from web3 import Web3
#
# from prediction_market_agent_tooling.markets.seer.price_manager import PriceManager
# from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
#     SeerSubgraphHandler,
# )
# from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
#
#
# def test_get_price_for_market() -> None:
#     market_id = Web3.to_checksum_address("0x02cf28257f0ee4a83fad4b0abc1a82526708f7c2")
#     s = SeerSubgraphHandler()
#     market = s.get_market_by_id(HexBytes(HexStr(market_id)))
#     p = PriceManager(seer_market=market, seer_subgraph=s)
#     # price_yes = p.current_p_yes()
#     # token_address = Web3.to_checksum_address(
#     #    "0xc7C21F360918bab25894e6f0F6da3695734D9042"
#     # )  # yes
#     token_address = Web3.to_checksum_address(
#         "0x11d4302ed96b3e46580f4cb09d33d087488d7344"
#     )  # no
#     price = p.get_token_price_from_pools(token=token_address)
#     print("end")
