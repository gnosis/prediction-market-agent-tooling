from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


class MinimalisticToken(BaseModel):
    sellToken: ChecksumAddress
    buyToken: ChecksumAddress


class Order(BaseModel):
    uid: str
    sellToken: str
    buyToken: str
    creationDate: DatetimeUTC
