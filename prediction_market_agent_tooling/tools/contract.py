import json
import os
import time
import typing as t
from contextlib import contextmanager

import eth_abi
from eth_abi.exceptions import DecodingError
from pydantic import BaseModel, field_validator
from web3 import Web3
from web3.constants import CHECKSUM_ADDRESSS_ZERO, HASH_ZERO
from web3.contract.contract import Contract as Web3Contract

from prediction_market_agent_tooling.chains import GNOSIS_CHAIN_ID, POLYGON_CHAIN_ID
from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChainID,
    ChecksumAddress,
    CollateralToken,
    HexAddress,
    HexBytes,
    HexStr,
    Nonce,
    OutcomeWei,
    TxParams,
    TxReceipt,
    Wei,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.utils import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import (
    call_function_on_contract,
    send_function_on_contract_tx,
    send_function_on_contract_tx_using_safe,
)


def abi_field_validator(value: str) -> ABI:
    if value.endswith(".json"):
        with open(value) as f:
            value = f.read()

    try:
        json.loads(value)  # Test if it's valid JSON content.
        return ABI(value)
    except json.decoder.JSONDecodeError:
        raise ValueError(f"Invalid ABI: {value}")


@contextmanager
def wait_until_nonce_changed(
    for_address: ChecksumAddress, timeout: int = 10, sleep_time: int = 1
) -> t.Generator[None, None, None]:
    current_nonce = ContractOnGnosisChain.get_transaction_count(for_address)
    yield
    start_monotonic = time.monotonic()
    while (
        time.monotonic() - start_monotonic < timeout
        and current_nonce == ContractOnGnosisChain.get_transaction_count(for_address)
    ):
        time.sleep(sleep_time)


class ContractBaseClass(BaseModel):
    """
    Base class holding the basic requirements and tools used for every contract.
    """

    CHAIN_ID: t.ClassVar[ChainID]

    abi: ABI
    address: ChecksumAddress

    _abi_field_validator = field_validator("abi", mode="before")(abi_field_validator)
    _cache: dict[
        str, t.Any
    ] = (
        {}
    )  # Can be used to hold values that aren't going to change after getting them for the first time, as for example `symbol` of an ERC-20 token.

    @classmethod
    def merge_contract_abis(cls, contracts: list["ContractBaseClass"]) -> ABI:
        merged_abi: list[dict[t.Any, t.Any]] = sum(
            (json.loads(contract.abi) for contract in contracts), []
        )
        return abi_field_validator(json.dumps(merged_abi))

    def get_web3_contract(self, web3: Web3 | None = None) -> Web3Contract:
        web3 = web3 or self.get_web3()
        return web3.eth.contract(address=self.address, abi=self.abi)

    def call(
        self,
        function_name: str,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        web3: Web3 | None = None,
    ) -> t.Any:
        """
        Used for reading from the contract.
        """
        web3 = web3 or self.get_web3()
        return call_function_on_contract(
            web3=web3,
            contract_address=self.address,
            contract_abi=self.abi,
            function_name=function_name,
            function_params=function_params,
        )

    def send(
        self,
        api_keys: APIKeys,
        function_name: str,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        tx_params: t.Optional[TxParams] = None,
        timeout: int = 180,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Used for changing a state (writing) to the contract.
        """

        if api_keys.safe_address_checksum:
            return send_function_on_contract_tx_using_safe(
                web3=web3 or self.get_web3(),
                contract_address=self.address,
                contract_abi=self.abi,
                from_private_key=api_keys.bet_from_private_key,
                safe_address=api_keys.safe_address_checksum,
                function_name=function_name,
                function_params=function_params,
                tx_params=tx_params,
                timeout=timeout,
            )
        return send_function_on_contract_tx(
            web3=web3 or self.get_web3(),
            contract_address=self.address,
            contract_abi=self.abi,
            from_private_key=api_keys.bet_from_private_key,
            function_name=function_name,
            function_params=function_params,
            tx_params=tx_params,
            timeout=timeout,
        )

    def send_with_value(
        self,
        api_keys: APIKeys,
        function_name: str,
        amount_wei: Wei,
        function_params: t.Optional[list[t.Any] | dict[str, t.Any]] = None,
        tx_params: t.Optional[TxParams] = None,
        timeout: int = 180,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Used for changing a state (writing) to the contract, including sending chain's native currency.
        """
        return self.send(
            api_keys=api_keys,
            function_name=function_name,
            function_params=function_params,
            tx_params={"value": amount_wei.value, **(tx_params or {})},
            timeout=timeout,
            web3=web3,
        )

    @classmethod
    def get_transaction_count(cls, for_address: ChecksumAddress) -> Nonce:
        return cls.get_web3().eth.get_transaction_count(for_address)

    @classmethod
    def get_web3(cls) -> Web3:
        return RPCConfig().get_web3()


class ContractProxyBaseClass(ContractBaseClass):
    """
    Contract base class for proxy contracts.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/proxy.abi.json"
        )
    )

    def implementation(self, web3: Web3 | None = None) -> ChecksumAddress:
        address = self.call("implementation", web3=web3)
        return Web3.to_checksum_address(address)


class ContractERC20BaseClass(ContractBaseClass):
    """
    Contract base class extended by ERC-20 standard methods.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/erc20.abi.json"
        )
    )

    def symbol(self, web3: Web3 | None = None) -> str:
        symbol: str = self.call("symbol", web3=web3)
        return symbol

    def symbol_cached(self, web3: Web3 | None = None) -> str:
        web3 = web3 or self.get_web3()
        cache_key = create_contract_method_cache_key(self.symbol, web3)
        if cache_key not in self._cache:
            self._cache[cache_key] = self.symbol(web3=web3)
        value: str = self._cache[cache_key]
        return value

    def allowance(
        self,
        owner: ChecksumAddress,
        for_address: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> Wei:
        allowance_for_user: int = self.call(
            "allowance", function_params=[owner, for_address], web3=web3
        )
        return Wei(allowance_for_user)

    def approve(
        self,
        api_keys: APIKeys,
        for_address: ChecksumAddress,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="approve",
            function_params=[
                for_address,
                amount_wei,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def transferFrom(
        self,
        api_keys: APIKeys,
        sender: ChecksumAddress,
        recipient: ChecksumAddress,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="transferFrom",
            function_params=[sender, recipient, amount_wei],
            tx_params=tx_params,
            web3=web3,
        )

    def balanceOf(self, for_address: ChecksumAddress, web3: Web3 | None = None) -> Wei:
        balance = Wei(self.call("balanceOf", [for_address], web3=web3))
        return balance

    def balance_of_in_tokens(
        self, for_address: ChecksumAddress, web3: Web3 | None = None
    ) -> CollateralToken:
        return self.balanceOf(for_address, web3=web3).as_token


class ContractDepositableWrapperERC20BaseClass(ContractERC20BaseClass):
    """
    ERC-20 standard base class extended for wrapper tokens.
    Although this is not a standard, it's seems to be a common pattern for wrapped tokens (at least it checks out for wxDai and wETH).
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../abis/depositablewrapper_erc20.abi.json",
        )
    )

    def deposit(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send_with_value(
            api_keys=api_keys,
            function_name="deposit",
            amount_wei=amount_wei,
            tx_params=tx_params,
            web3=web3,
        )

    def withdraw(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="withdraw",
            function_params=[amount_wei],
            tx_params=tx_params,
            web3=web3,
        )


class ContractERC4626BaseClass(ContractERC20BaseClass):
    """
    Class for ERC-4626, which is a superset for ERC-20.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/erc4626.abi.json"
        )
    )

    def asset(self, web3: Web3 | None = None) -> ChecksumAddress:
        address = self.call("asset", web3=web3)
        return Web3.to_checksum_address(address)

    def deposit(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        receiver: ChecksumAddress | None = None,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        receiver = receiver or api_keys.bet_from_address
        return self.send(
            api_keys=api_keys,
            function_name="deposit",
            function_params=[amount_wei, receiver],
            tx_params=tx_params,
            web3=web3,
        )

    def withdraw(
        self,
        api_keys: APIKeys,
        assets_wei: Wei,
        receiver: ChecksumAddress | None = None,
        owner: ChecksumAddress | None = None,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        # assets_wei is the amount of assets (underlying erc20 token amount) we want to withdraw.
        receiver = receiver or api_keys.bet_from_address
        owner = owner or api_keys.bet_from_address
        return self.send(
            api_keys=api_keys,
            function_name="withdraw",
            function_params=[assets_wei, receiver, owner],
            tx_params=tx_params,
            web3=web3,
        )

    def withdraw_in_shares(
        self, api_keys: APIKeys, shares_wei: Wei, web3: Web3 | None = None
    ) -> TxReceipt:
        # shares_wei is the amount of shares we want to withdraw.
        assets = self.convertToAssets(shares_wei, web3=web3)
        return self.withdraw(api_keys=api_keys, assets_wei=assets, web3=web3)

    def convertToShares(self, assets: Wei, web3: Web3 | None = None) -> Wei:
        shares = Wei(self.call("convertToShares", [assets], web3=web3))
        return shares

    def convertToAssets(self, shares: Wei, web3: Web3 | None = None) -> Wei:
        assets = Wei(self.call("convertToAssets", [shares], web3=web3))
        return assets

    def get_asset_token_contract(
        self, web3: Web3 | None = None
    ) -> ContractERC20BaseClass | ContractDepositableWrapperERC20BaseClass:
        web3 = web3 or self.get_web3()
        contract = init_collateral_token_contract(self.asset(), web3=web3)
        assert not isinstance(
            contract, ContractERC4626BaseClass
        ), "Asset token should be either Depositable Wrapper ERC-20 or ERC-20."  # Shrinking down possible types.
        return contract

    def get_asset_token_balance(
        self, for_address: ChecksumAddress, web3: Web3 | None = None
    ) -> Wei:
        asset_token_contract = self.get_asset_token_contract(web3=web3)
        return asset_token_contract.balanceOf(for_address, web3=web3)

    def deposit_asset_token(
        self, asset_value: Wei, api_keys: APIKeys, web3: Web3 | None = None
    ) -> TxReceipt:
        for_address = api_keys.bet_from_address
        web3 = web3 or self.get_web3()

        asset_token_contract = self.get_asset_token_contract(web3=web3)
        # Approve vault to withdraw the erc-20 token from the user.
        asset_token_contract.approve(api_keys, self.address, asset_value, web3=web3)

        # Deposit asset token (erc20) and we will receive shares in this vault.
        receipt = self.deposit(api_keys, asset_value, for_address, web3=web3)

        return receipt

    def get_in_shares(self, amount: Wei, web3: Web3 | None = None) -> Wei:
        # We send erc20 to the vault and receive shares in return, which can have a different value.
        return self.convertToShares(amount, web3=web3)


class ContractWrapped1155BaseClass(ContractERC20BaseClass):
    """Wrapped 1155 contract from Seer (https://gnosisscan.io/address/0x2f9c49974ad8b9b31424d9dc812667b16310ca50#readContract)
    Source code - https://github.com/seer-pm/demo/blob/main/contracts/src/interaction/1155-to-20/Wrapped1155Factory.sol#L224
    This contract inherits from ERC20 and contains additional properties, such as multiToken (conditional Token contract implementation)
    and tokenId (token identifier). Goal is to wrap individual tokens into a standalone ERC20 token.
    """

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../abis/erc1155.abi.json"
        )
    )


class OwnableContract(ContractBaseClass):
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../abis/ownable.abi.json",
        )
    )

    def owner(self, web3: Web3 | None = None) -> ChecksumAddress:
        owner = Web3.to_checksum_address(self.call("owner", web3=web3))
        return owner


class ContractERC721BaseClass(ContractBaseClass):
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../abis/erc721.abi.json",
        )
    )

    def safeMint(
        self,
        api_keys: APIKeys,
        to_address: ChecksumAddress,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="safeMint",
            function_params=[to_address],
            tx_params=tx_params,
            web3=web3,
        )

    def balanceOf(self, owner: ChecksumAddress, web3: Web3 | None = None) -> Wei:
        balance = Wei(self.call("balanceOf", [owner], web3=web3))
        return balance

    def owner_of(self, token_id: int, web3: Web3 | None = None) -> ChecksumAddress:
        owner = Web3.to_checksum_address(self.call("ownerOf", [token_id], web3=web3))
        return owner

    def name(self, web3: Web3 | None = None) -> str:
        name: str = self.call("name", web3=web3)
        return name

    def symbol(self, web3: Web3 | None = None) -> str:
        symbol: str = self.call("symbol", web3=web3)
        return symbol

    def tokenURI(self, tokenId: int, web3: Web3 | None = None) -> str:
        uri: str = self.call("tokenURI", [tokenId], web3=web3)
        return uri

    def safeTransferFrom(
        self,
        api_keys: APIKeys,
        from_address: ChecksumAddress,
        to_address: ChecksumAddress,
        tokenId: int,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="safeTransferFrom",
            function_params=[from_address, to_address, tokenId],
            tx_params=tx_params,
            web3=web3,
        )


class ContractOwnableERC721BaseClass(ContractERC721BaseClass, OwnableContract):
    # We add dummy addresses below so that we can reference .abi later.
    abi: ABI = ContractBaseClass.merge_contract_abis(
        [
            ContractERC721BaseClass(address=ChecksumAddress(CHECKSUM_ADDRESSS_ZERO)),
            OwnableContract(address=ChecksumAddress(CHECKSUM_ADDRESSS_ZERO)),
        ]
    )


class ContractOnGnosisChain(ContractBaseClass):
    """
    Contract base class with Gnosis Chain configuration.
    """

    CHAIN_ID = GNOSIS_CHAIN_ID


class ContractOnPolygonChain(ContractBaseClass):
    """
    Contract base class with Gnosis Chain configuration.
    """

    CHAIN_ID = POLYGON_CHAIN_ID


class ContractProxyOnGnosisChain(ContractProxyBaseClass, ContractOnGnosisChain):
    """
    Proxy contract base class with Gnosis Chain configuration.
    """


class ContractERC20OnGnosisChain(ContractERC20BaseClass, ContractOnGnosisChain):
    """
    ERC-20 standard base class with Gnosis Chain configuration.
    """


class ContractOwnableERC721OnGnosisChain(
    ContractOwnableERC721BaseClass, ContractOnGnosisChain
):
    """
    Ownable ERC-721 standard base class with Gnosis Chain configuration.
    """


class ContractDepositableWrapperERC20OnGnosisChain(
    ContractDepositableWrapperERC20BaseClass, ContractERC20OnGnosisChain
):
    """
    Depositable Wrapper ERC-20 standard base class with Gnosis Chain configuration.
    """


class ContractWrapped1155OnGnosisChain(
    ContractWrapped1155BaseClass, ContractERC20OnGnosisChain
):
    pass


class ContractERC4626OnGnosisChain(
    ContractERC4626BaseClass, ContractERC20OnGnosisChain
):
    """
    ERC-4626 standard base class with Gnosis Chain configuration.
    """

    def get_asset_token_contract(
        self, web3: Web3 | None = None
    ) -> ContractERC20OnGnosisChain | ContractDepositableWrapperERC20OnGnosisChain:
        return to_gnosis_chain_contract(super().get_asset_token_contract(web3=web3))


class PayoutRedemptionEvent(BaseModel):
    redeemer: HexAddress
    collateralToken: HexAddress
    parentCollectionId: HexBytes
    conditionId: HexBytes
    indexSets: list[int]
    payout: Wei


class ConditionPreparationEvent(BaseModel):
    conditionId: HexBytes
    oracle: HexAddress
    questionId: HexBytes
    outcomeSlotCount: int


class ConditionalTokenContract(ContractBaseClass):
    # Contract ABI taken from https://gnosisscan.io/address/0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../abis/omen_fpmm_conditionaltokens.abi.json",
        )
    )

    def getConditionId(
        self,
        question_id: HexBytes,
        oracle_address: ChecksumAddress,
        outcomes_slot_count: int,
        web3: Web3 | None = None,
    ) -> HexBytes:
        id_ = HexBytes(
            self.call(
                "getConditionId",
                [oracle_address, question_id, outcomes_slot_count],
                web3=web3,
            )
        )
        return id_

    def balanceOf(
        self, from_address: ChecksumAddress, position_id: int, web3: Web3 | None = None
    ) -> OutcomeWei:
        balance = OutcomeWei(
            self.call("balanceOf", [from_address, position_id], web3=web3)
        )
        return balance

    def getCollectionId(
        self,
        parent_collection_id: HexStr,
        condition_id: HexBytes,
        index_set: int,
        web3: Web3 | None = None,
    ) -> HexBytes:
        collection_id = HexBytes(
            self.call(
                "getCollectionId",
                [parent_collection_id, condition_id, index_set],
                web3=web3,
            )
        )
        return collection_id

    def getPositionId(
        self,
        collateral_token_address: ChecksumAddress,
        collection_id: HexBytes,
        web3: Web3 | None = None,
    ) -> int:
        position_id: int = self.call(
            "getPositionId",
            [collateral_token_address, collection_id],
            web3=web3,
        )
        return position_id

    def mergePositions(
        self,
        api_keys: APIKeys,
        collateral_token_address: ChecksumAddress,
        conditionId: HexBytes,
        index_sets: t.List[int],
        amount: OutcomeWei,
        parent_collection_id: HexStr = HASH_ZERO,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="mergePositions",
            function_params=[
                collateral_token_address,
                parent_collection_id,
                conditionId,
                index_sets,
                amount,
            ],
            web3=web3,
        )

    def redeemPositions(
        self,
        api_keys: APIKeys,
        collateral_token_address: HexAddress,
        condition_id: HexBytes,
        index_sets: t.List[int],
        parent_collection_id: HexStr = HASH_ZERO,
        web3: Web3 | None = None,
    ) -> PayoutRedemptionEvent:
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="redeemPositions",
            function_params=[
                collateral_token_address,
                parent_collection_id,
                condition_id,
                index_sets,
            ],
            web3=web3,
        )
        redeem_event_logs = (
            self.get_web3_contract(web3=web3)
            .events.PayoutRedemption()
            .process_receipt(receipt_tx)
        )
        redeem_event = PayoutRedemptionEvent(**redeem_event_logs[0]["args"])
        return redeem_event

    def getOutcomeSlotCount(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> int:
        count: int = self.call("getOutcomeSlotCount", [condition_id], web3=web3)
        return count

    def does_condition_exists(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> bool:
        return self.getOutcomeSlotCount(condition_id, web3=web3) > 0

    def is_condition_resolved(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> bool:
        # from ConditionalTokens.redeemPositions:
        # uint den = payoutDenominator[conditionId]; require(den > 0, "result for condition not received yet");
        payout_for_condition = self.payoutDenominator(condition_id, web3=web3)
        return payout_for_condition > 0

    def payoutDenominator(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> int:
        payoutForCondition: int = self.call(
            "payoutDenominator", [condition_id], web3=web3
        )
        return payoutForCondition

    def setApprovalForAll(
        self,
        api_keys: APIKeys,
        for_address: ChecksumAddress,
        approve: bool,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="setApprovalForAll",
            function_params=[
                for_address,
                approve,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def prepareCondition(
        self,
        api_keys: APIKeys,
        oracle_address: ChecksumAddress,
        question_id: HexBytes,
        outcomes_slot_count: int,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> ConditionPreparationEvent:
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="prepareCondition",
            function_params=[
                oracle_address,
                question_id,
                outcomes_slot_count,
            ],
            tx_params=tx_params,
            web3=web3,
        )

        event_logs = (
            self.get_web3_contract(web3=web3)
            .events.ConditionPreparation()
            .process_receipt(receipt_tx)
        )
        cond_event = ConditionPreparationEvent(**event_logs[0]["args"])

        return cond_event


class DebuggingContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0x5Aa82E068aE6a6a1C26c42E5a59520a74Cdb8998#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../abis/debuggingcontract.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x5Aa82E068aE6a6a1C26c42E5a59520a74Cdb8998"
    )

    def getNow(
        self,
        web3: Web3 | None = None,
    ) -> int:
        now: int = self.call(
            function_name="getNow",
            web3=web3,
        )
        return now

    def get_now(
        self,
        web3: Web3 | None = None,
    ) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.getNow(web3))

    def inc(
        self,
        api_keys: APIKeys,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="inc",
            web3=web3,
        )


def contract_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    web3: Web3,
    function_arg_types: list[str] | None = None,
    look_for_proxy_contract: bool = True,
) -> bool:
    function_signature = f"{function_name}({','.join(function_arg_types or [])})"
    function_selector = web3.keccak(text=function_signature)[0:4].hex()[2:]
    # 1. Check directly in bytecode
    bytecode = web3.eth.get_code(contract_address).hex()
    if function_selector in bytecode:
        return True
    contract_code = web3.eth.get_code(contract_address).hex()
    implements = function_selector in contract_code

    # If not found directly and we should check proxies
    if not implements and look_for_proxy_contract:
        # Case 1: Check if it's a standard proxy (has implementation() function)
        if contract_implements_function(
            contract_address, "implementation", web3, look_for_proxy_contract=False
        ):
            # Get the implementation address and check the function there
            implementation_address = ContractProxyOnGnosisChain(
                address=contract_address
            ).implementation()
            implements = contract_implements_function(
                implementation_address,
                function_name=function_name,
                web3=web3,
                function_arg_types=function_arg_types,
                look_for_proxy_contract=False,
            )
        else:
            # Case 2: Check if it's a minimal proxy contract
            implements = minimal_proxy_implements_function(
                contract_address=contract_address,
                function_name=function_name,
                web3=web3,
                function_arg_types=function_arg_types,
            ) or seer_minimal_proxy_implements_function(
                contract_address=contract_address,
                function_name=function_name,
                web3=web3,
                function_arg_types=function_arg_types,
            )

    return implements


def minimal_proxy_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    web3: Web3,
    function_arg_types: list[str] | None = None,
) -> bool:
    try:
        # Read storage slot 0 which should contain the implementation address in minimal proxies
        raw_slot_0 = web3.eth.get_storage_at(contract_address, 0)
        singleton_address = eth_abi.decode(["address"], raw_slot_0)[0]
        # Recurse into singleton
        return contract_implements_function(
            Web3.to_checksum_address(singleton_address),
            function_name=function_name,
            web3=web3,
            function_arg_types=function_arg_types,
            look_for_proxy_contract=False,
        )
    except DecodingError:
        logger.info(f"Error decoding contract address for singleton")
        return False


def seer_minimal_proxy_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    web3: Web3,
    function_arg_types: list[str] | None = None,
) -> bool:
    try:
        # Read address between specific indices to find logic contract
        bytecode = web3.eth.get_code(contract_address)
        logic_contract_address = bytecode[11:31]
        if not Web3.is_address(logic_contract_address):
            return False

        return contract_implements_function(
            Web3.to_checksum_address(logic_contract_address),
            function_name=function_name,
            web3=web3,
            function_arg_types=function_arg_types,
            look_for_proxy_contract=False,
        )
    except DecodingError:
        logger.info("Error decoding contract address on seer minimal proxy")
        return False


def init_collateral_token_contract(
    address: ChecksumAddress, web3: Web3 | None
) -> ContractERC20BaseClass:
    """
    Checks if the given contract is Depositable ERC-20, ERC-20 or ERC-4626 and returns the appropriate class instance.
    Throws an error if the contract is neither of them.
    """
    web3 = web3 or RPCConfig().get_web3()

    if contract_implements_function(address, "asset", web3=web3):
        return ContractERC4626BaseClass(address=address)

    elif contract_implements_function(
        address,
        "deposit",
        web3=web3,
    ):
        return ContractDepositableWrapperERC20BaseClass(address=address)

    elif contract_implements_function(
        address,
        "multiToken",
        web3=web3,
    ):
        return ContractWrapped1155BaseClass(address=address)

    elif contract_implements_function(
        address,
        "balanceOf",
        web3=web3,
        function_arg_types=["address"],
    ):
        return ContractERC20BaseClass(address=address)

    else:
        raise ValueError(
            f"Contract at {address} is neither Depositable ERC-20, ERC-20 nor ERC-4626."
        )


def to_gnosis_chain_contract(
    contract: ContractERC20BaseClass,
) -> ContractERC20OnGnosisChain:
    if isinstance(contract, ContractERC4626BaseClass):
        return ContractERC4626OnGnosisChain(address=contract.address)
    elif isinstance(contract, ContractDepositableWrapperERC20BaseClass):
        return ContractDepositableWrapperERC20OnGnosisChain(address=contract.address)
    elif isinstance(contract, ContractWrapped1155BaseClass):
        return ContractWrapped1155OnGnosisChain(address=contract.address)
    elif isinstance(contract, ContractERC20BaseClass):
        return ContractERC20OnGnosisChain(address=contract.address)
    else:
        raise ValueError("Unsupported contract type")


def create_contract_method_cache_key(
    method: t.Callable[[t.Any], t.Any], web3: Web3
) -> str:
    return f"{method.__name__}-{str(web3.provider)}"
