import json
import os
import random
import typing as t
from datetime import datetime
from enum import Enum

from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    OmenOutcomeToken,
    PrivateKey,
    TxParams,
    TxReceipt,
    Wei,
    xdai_type,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
    ContractOnGnosisChain,
    abi_field_validator,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


class OmenOracleContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xAB16D643bA051C11962DA645f74632d3130c81E2#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_oracle.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xAB16D643bA051C11962DA645f74632d3130c81E2"
    )

    def realitio(self) -> ChecksumAddress:
        realitio_address: ChecksumAddress = self.call("realitio")
        return realitio_address

    def conditionalTokens(self) -> ChecksumAddress:
        realitio_address: ChecksumAddress = self.call("conditionalTokens")
        return realitio_address


class OmenConditionalTokenContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_fpmm_conditionaltokens.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"
    )

    def getConditionId(
        self,
        question_id: HexBytes,
        oracle_address: ChecksumAddress,
        outcomes_slot_count: int,
    ) -> HexBytes:
        id_: HexBytes = self.call(
            "getConditionId",
            [oracle_address, question_id, outcomes_slot_count],
        )
        return id_

    def getOutcomeSlotCount(
        self,
        condition_id: HexBytes,
    ) -> int:
        count: int = self.call(
            "getOutcomeSlotCount",
            [condition_id],
        )
        return count

    def does_condition_exists(
        self,
        condition_id: HexBytes,
    ) -> bool:
        return self.getOutcomeSlotCount(condition_id) > 0

    def setApprovalForAll(
        self,
        for_address: ChecksumAddress,
        approve: bool,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="setApprovalForAll",
            function_params=[
                for_address,
                approve,
            ],
            tx_params=tx_params,
        )

    def prepareCondition(
        self,
        oracle_address: ChecksumAddress,
        question_id: HexBytes,
        outcomes_slot_count: int,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="prepareCondition",
            function_params=[
                oracle_address,
                question_id,
                outcomes_slot_count,
            ],
            tx_params=tx_params,
        )


class OmenFixedProductMarketMakerContract(ContractOnGnosisChain):
    # File content taken from https://github.com/protofire/omen-exchange/blob/master/app/src/abi/marketMaker.json.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../../abis/omen_fpmm.abi.json"
        )
    )

    # ! Note: This doesn't have a fixed contract address, as this is something created by the `OmenFixedProductMarketMakerFactory`.
    # Factory contract at https://gnosisscan.io/address/0x9083a2b699c0a4ad06f63580bde2635d26a3eef0.

    def calcBuyAmount(
        self,
        investment_amount: Wei,
        outcome_index: int,
    ) -> OmenOutcomeToken:
        """
        Returns amount of shares we will get for the given outcome_index for the given investment amount.
        """
        calculated_shares: OmenOutcomeToken = self.call(
            "calcBuyAmount",
            [investment_amount, outcome_index],
        )
        return calculated_shares

    def calcSellAmount(
        self,
        return_amount: Wei,
        outcome_index: int,
    ) -> OmenOutcomeToken:
        """
        Returns amount of shares we will sell for the requested wei.
        """
        calculated_shares: OmenOutcomeToken = self.call(
            "calcSellAmount",
            [return_amount, outcome_index],
        )
        return calculated_shares

    def conditionalTokens(
        self,
    ) -> HexAddress:
        address: HexAddress = self.call(
            "conditionalTokens",
        )
        return address

    def buy(
        self,
        amount_wei: Wei,
        outcome_index: int,
        min_outcome_tokens_to_buy: OmenOutcomeToken,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="buy",
            function_params=[
                amount_wei,
                outcome_index,
                min_outcome_tokens_to_buy,
            ],
            tx_params=tx_params,
        )

    def sell(
        self,
        amount_wei: Wei,
        outcome_index: int,
        max_outcome_tokens_to_sell: OmenOutcomeToken,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="sell",
            function_params=[
                amount_wei,
                outcome_index,
                max_outcome_tokens_to_sell,
            ],
            tx_params=tx_params,
        )

    def addFunding(
        self,
        add_funding: Wei,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        """
        Funding is added in Weis (xDai) and then converted to shares.
        """
        # `addFunding` with `distribution_hint` can be used only during the market creation, so forcing empty here.
        distribution_hint: list[int] = []
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="addFunding",
            function_params=[add_funding, distribution_hint],
            tx_params=tx_params,
        )

    def removeFunding(
        self,
        remove_funding_shares: int,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        """
        Remove funding is done in shares.
        """
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="removeFunding",
            function_params=[remove_funding_shares],
            tx_params=tx_params,
        )


class WrappedxDaiContract(ContractERC20OnGnosisChain):
    # File content taken from https://gnosisscan.io/address/0xe91d153e0b41518a2ce8dd3d7944fa863463a97d#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../../abis/wxdai.abi.json"
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d"
    )


# Collateral token used on Omen is wrapped xDai.
OmenCollateralTokenContract = WrappedxDaiContract

OMEN_DEFAULT_MARKET_FEE = 0.02  # 2% fee from the buying shares amount.


class OmenFixedProductMarketMakerFactoryContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_fpmm_factory.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0"
    )

    def create2FixedProductMarketMaker(
        self,
        condition_id: HexBytes,
        initial_funds_wei: Wei,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        fee: float = OMEN_DEFAULT_MARKET_FEE,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        fee_wei = xdai_to_wei(
            xdai_type(fee)
        )  # We need to convert this to the wei units, but in reality it's % fee as stated in the `OMEN_DEFAULT_MARKET_FEE` variable.
        return self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="create2FixedProductMarketMaker",
            function_params=dict(
                saltNonce=random.randint(
                    0, 1000000
                ),  # See https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942.
                conditionalTokens=OmenConditionalTokenContract().address,
                collateralToken=OmenCollateralTokenContract().address,
                conditionIds=[condition_id],
                fee=fee_wei,
                initialFunds=initial_funds_wei,
                distributionHint=[],
            ),
            tx_params=tx_params,
        )


class Arbitrator(str, Enum):
    KLEROS = "kleros"
    DXDAO = "dxdao"


class OmenDxDaoContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xFe14059344b74043Af518d12931600C0f52dF7c5#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_dxdao.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xFe14059344b74043Af518d12931600C0f52dF7c5"
    )


class OmenKlerosContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xe40DD83a262da3f56976038F1554Fe541Fa75ecd#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_kleros.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xe40DD83a262da3f56976038F1554Fe541Fa75ecd"
    )


class OmenRealitioContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0x79e32aE03fb27B07C89c0c568F80287C01ca2E57#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_realitio.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
    )

    @staticmethod
    def get_arbitrator_contract(
        arbitrator: Arbitrator,
    ) -> ContractOnGnosisChain:
        if arbitrator == Arbitrator.KLEROS:
            return OmenKlerosContract()
        if arbitrator == Arbitrator.DXDAO:
            return OmenDxDaoContract()
        raise ValueError(f"Unknown arbitrator: {arbitrator}")

    def askQuestion(
        self,
        question: str,
        category: str,
        outcomes: list[str],
        language: str,
        arbitrator: Arbitrator,
        opening: datetime,
        from_address: ChecksumAddress,
        from_private_key: PrivateKey,
        nonce: int | None = None,
        tx_params: t.Optional[TxParams] = None,
    ) -> HexBytes:
        """
        After the question is created, you can find it at https://reality.eth.link/app/#!/creator/{from_address}.
        """
        arbitrator_contract_address = self.get_arbitrator_contract(arbitrator).address
        # See https://realitio.github.io/docs/html/contracts.html#templates
        # for possible template ids and how to format the question.
        template_id = 2
        realitio_question = "␟".join(
            [
                question,
                json.dumps(outcomes),
                category,
                language,
            ]
        )
        receipt_tx = self.send(
            from_address=from_address,
            from_private_key=from_private_key,
            function_name="askQuestion",
            function_params=dict(
                template_id=template_id,
                question=realitio_question,
                arbitrator=arbitrator_contract_address,
                timeout=86400,  # See https://github.com/protofire/omen-exchange/blob/2cfdf6bfe37afa8b169731d51fea69d42321d66c/app/src/util/networks.ts#L278.
                opening_ts=int(opening.timestamp()),
                nonce=(
                    nonce if nonce is not None else random.randint(0, 1000000)
                ),  # Two equal questions need to have different nonces.
            ),
            tx_params=tx_params,
        )
        question_id: HexBytes = receipt_tx["logs"][0]["topics"][
            1
        ]  # The question id is available in the first emitted log, in the second topic.
        return question_id
