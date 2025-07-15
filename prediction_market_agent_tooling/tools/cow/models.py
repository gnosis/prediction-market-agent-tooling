from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import utcnow


class MinimalisticTrade(BaseModel):
    sellToken: ChecksumAddress
    buyToken: ChecksumAddress
    orderUid: HexBytes
    txHash: HexBytes


class Order(BaseModel):
    uid: str
    sellToken: str
    buyToken: str
    creationDate: DatetimeUTC


class RateLimit(SQLModel, table=True):
    __tablename__ = "rate_limit"
    id: str = Field(primary_key=True)
    last_called_at: DatetimeUTC = Field(default_factory=utcnow)
