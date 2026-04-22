import os
import typing as t

from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexBytes,
    OutcomeWei,
    Wei,
)
from prediction_market_agent_tooling.markets.polymarket.constants import (
    STATA_POL_USDCN_ADDRESS,
    WRAPPED_1155_FACTORY_ADDRESS,
)
from prediction_market_agent_tooling.tools.contract import (
    ConditionalTokenContract,
    ContractDepositableWrapperERC20OnPolygonChain,
    ContractERC20BaseClass,
    ContractERC4626OnPolygonChain,
    ContractOnPolygonChain,
    PayoutRedemptionEvent,
    abi_field_validator,
)
from prediction_market_agent_tooling.tools.web3_utils import (
    SafeBatchCall,
    encode_contract_call,
    send_safe_batch_tx,
)


class WPOLContract(ContractDepositableWrapperERC20OnPolygonChain):
    # Wrapped POL (formerly WMATIC) on Polygon.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"
    )


class USDCContract(ContractERC20BaseClass, ContractOnPolygonChain):
    # Native USDC on Polygon.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
    )


class USDCeContract(ContractERC20BaseClass, ContractOnPolygonChain):
    # USDC.e (bridged) is used by Polymarket.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    )


class StataPolUSDCnContract(ContractERC4626OnPolygonChain):
    # Aave V3 static ERC-4626 wrapper over the aToken for USDC native on
    # Polygon. Asset is USDC native (0x3c499c54…). Non-rebasing.
    address: ChecksumAddress = STATA_POL_USDCN_ADDRESS


class Wrapped1155FactoryContract(ContractOnPolygonChain):
    """Canonical Gnosis Guild Wrapped1155Factory.

    Wraps any ERC-1155 token ID into a per-(multiToken, tokenId, metadata)
    ERC-20 via deterministic CREATE2. Lets CTF outcome tokens trade as
    normal ERC-20s on CoW, Uniswap, Balancer, etc.
    """

    address: ChecksumAddress = WRAPPED_1155_FACTORY_ADDRESS
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/wrapped_1155_factory.abi.json",
        )
    )

    def get_wrapped_1155(
        self,
        multi_token: ChecksumAddress,
        token_id: int,
        data: bytes,
        web3: Web3 | None = None,
    ) -> ChecksumAddress:
        """Return the CREATE2 address of the wrapped ERC-20 (may not yet be deployed)."""
        addr: str = self.call(
            "getWrapped1155", [multi_token, token_id, data], web3=web3
        )
        return Web3.to_checksum_address(addr)

    @staticmethod
    def encode_metadata(name: str, symbol: str, decimals: int = 6) -> bytes:
        """Pack (name, symbol, decimals) into the 65-byte `data` payload.

        The factory writes the first 32 bytes to the ERC-20 `_name` storage
        slot, the next 32 to `_symbol`, and the last byte to `_decimals`.
        Names/symbols use Solidity's "short string" form: up to 31 UTF-8
        bytes, right-padded with zeros, with `length * 2` in the final byte.
        """

        def _short_string(s: str) -> bytes:
            b = s.encode("utf-8")
            if len(b) > 31:
                raise ValueError(
                    f"string too long for ERC-20 short-string form "
                    f"(max 31 bytes, got {len(b)}): {s!r}"
                )
            return b.ljust(31, b"\x00") + bytes([len(b) * 2])

        if not 0 <= decimals < 256:
            raise ValueError(f"decimals must fit in one byte, got {decimals}")
        return _short_string(name) + _short_string(symbol) + bytes([decimals])


class Wrapped1155Contract(ContractERC20BaseClass, ContractOnPolygonChain):
    """Per-position ERC-20 produced by `Wrapped1155FactoryContract`.

    Instantiate with the CREATE2 address returned by
    `Wrapped1155FactoryContract.get_wrapped_1155()`. Uses the standard
    ERC-20 ABI; `factory.unwrap(...)` is the way to burn back to ERC-1155.
    """


class PolymarketConditionalTokenContract(
    ConditionalTokenContract, ContractOnPolygonChain
):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    )

    def approve_if_not_approved(
        self, api_keys: APIKeys, for_address: ChecksumAddress, web3: Web3 | None = None
    ) -> None:
        is_approved = self.isApprovedForAll(
            owner=api_keys.public_key, for_address=for_address, web3=web3
        )
        if not is_approved:
            self.setApprovalForAll(
                api_keys=api_keys, for_address=for_address, approve=True, web3=web3
            )

    def mint_full_set(
        self,
        api_keys: APIKeys,
        collateral_token: ContractERC20BaseClass,
        condition_id: HexBytes,
        amount: Wei,
        outcome_slot_count: int = 2,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """Approve collateral and split into a full outcome set.

        Works with any ERC-20 collateral (USDC.e, stataPolUSDCn, …) — the
        resulting ERC1155 position IDs are keyed by (condition, collateral),
        so mint_full_set(…, USDC.e) and mint_full_set(…, stata) produce
        distinct YES/NO tokens for the same market.
        """
        collateral_token.approve(
            api_keys=api_keys,
            for_address=self.address,
            amount_wei=amount,
            web3=web3,
        )
        return self.splitPosition(
            api_keys=api_keys,
            collateral_token=collateral_token.address,
            condition_id=condition_id,
            outcome_slot_count=outcome_slot_count,
            amount_wei=amount,
            web3=web3,
        )

    def merge_full_set(
        self,
        api_keys: APIKeys,
        collateral_token: ContractERC20BaseClass,
        condition_id: HexBytes,
        amount: OutcomeWei,
        outcome_slot_count: int = 2,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """Burn a full outcome set back into collateral.

        Caller must hold `amount` of every outcome token for the condition;
        CTF will revert otherwise.
        """
        index_sets: t.List[int] = [2**i for i in range(outcome_slot_count)]
        return self.mergePositions(
            api_keys=api_keys,
            collateral_token_address=collateral_token.address,
            conditionId=condition_id,
            index_sets=index_sets,
            amount=amount,
            web3=web3,
        )

    def redeem_full_set(
        self,
        api_keys: APIKeys,
        collateral_token: ContractERC20BaseClass,
        condition_id: HexBytes,
        outcome_slot_count: int = 2,
        web3: Web3 | None = None,
    ) -> PayoutRedemptionEvent:
        """Redeem outcome tokens to collateral after the market has resolved."""
        index_sets: t.List[int] = [2**i for i in range(outcome_slot_count)]
        return self.redeemPositions(
            api_keys=api_keys,
            collateral_token_address=collateral_token.address,
            condition_id=condition_id,
            index_sets=index_sets,
            web3=web3,
        )

    def mint_full_set_via_safe_batch(
        self,
        api_keys: APIKeys,
        collateral_token: ContractERC20BaseClass,
        condition_id: HexBytes,
        amount: Wei,
        outcome_slot_count: int = 2,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """Atomic approve + splitPosition through a Safe MultiSend batch.

        Requires `api_keys.safe_address_checksum`. Combines the two legs into
        a single on-chain tx — either both succeed or both revert, and we pay
        gas once.
        """
        safe_address = api_keys.safe_address_checksum
        if safe_address is None:
            raise ValueError(
                "mint_full_set_via_safe_batch requires a configured Safe "
                "(set SAFE_ADDRESS). Use mint_full_set for the EOA path."
            )
        web3 = web3 or self.get_web3()
        calls = [
            self._collateral_approve_call(web3, collateral_token, self.address, amount),
            self._split_position_call(
                web3, collateral_token, condition_id, outcome_slot_count, amount
            ),
        ]
        return send_safe_batch_tx(
            web3=web3,
            safe_address=safe_address,
            from_private_key=api_keys.bet_from_private_key,
            calls=calls,
        )

    @staticmethod
    def _collateral_approve_call(
        web3: Web3,
        collateral_token: ContractERC20BaseClass,
        spender: ChecksumAddress,
        amount: Wei,
    ) -> SafeBatchCall:
        """Build a `SafeBatchCall` for `collateral.approve(spender, amount)`."""
        return encode_contract_call(
            web3=web3,
            contract_address=collateral_token.address,
            contract_abi=collateral_token.abi,
            function_name="approve",
            function_params=[spender, amount],
        )

    def _split_position_call(
        self,
        web3: Web3,
        collateral_token: ContractERC20BaseClass,
        condition_id: HexBytes,
        outcome_slot_count: int,
        amount: Wei,
    ) -> SafeBatchCall:
        """Build a `SafeBatchCall` for `CTF.splitPosition(collateral, 0x0, cond, partition, amount)`."""
        partition: list[int] = [2**i for i in range(outcome_slot_count)]
        return encode_contract_call(
            web3=web3,
            contract_address=self.address,
            contract_abi=self.abi,
            function_name="splitPosition",
            function_params=[
                collateral_token.address,
                bytes(HexBytes(b"\x00" * 32)),
                bytes(condition_id),
                partition,
                amount,
            ],
        )

    def _erc1155_transfer_call(
        self,
        web3: Web3,
        frm: ChecksumAddress,
        to: ChecksumAddress,
        position_id: int,
        amount: OutcomeWei,
        data: bytes = b"",
    ) -> SafeBatchCall:
        """Build a `SafeBatchCall` for ERC1155 `safeTransferFrom(frm, to, id, amount, data)`."""
        return encode_contract_call(
            web3=web3,
            contract_address=self.address,
            contract_abi=self.abi,
            function_name="safeTransferFrom",
            function_params=[frm, to, position_id, amount.value, data],
        )

    def _position_id_for(
        self,
        collateral_address: ChecksumAddress,
        condition_id: HexBytes,
        index_set: int,
        web3: Web3 | None = None,
    ) -> int:
        """Compute the ERC1155 positionId for a (collateral, condition, index_set)."""
        collection_id = self.getCollectionId(
            parent_collection_id=HexBytes(b"\x00" * 32),
            condition_id=condition_id,
            index_set=index_set,
            web3=web3,
        )
        return self.getPositionId(
            collateral_token_address=collateral_address,
            collection_id=collection_id,
            web3=web3,
        )
