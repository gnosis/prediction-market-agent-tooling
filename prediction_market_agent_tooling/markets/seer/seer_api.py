import httpx

from prediction_market_agent_tooling.gtypes import ChainID, ChecksumAddress
from prediction_market_agent_tooling.markets.seer.data_models import SeerTransaction
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import to_int_timestamp, utcnow


def get_seer_transactions(
    account: ChecksumAddress,
    chain_id: ChainID,
    start_time: DatetimeUTC | None = None,
    end_time: DatetimeUTC | None = None,
    timeout: int = 60,  # The endpoint is pretty slow to respond atm.
) -> list[SeerTransaction]:
    url = "https://app.seer.pm/.netlify/functions/get-transactions"
    params: dict[str, str | int] = {
        "account": account,
        "chainId": chain_id,
        "startTime": to_int_timestamp(start_time) if start_time else 0,
        "endTime": to_int_timestamp(end_time if end_time else utcnow()),
    }
    response = httpx.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    response_json = response.json()

    transactions = [SeerTransaction.model_validate(tx) for tx in response_json]
    return transactions
