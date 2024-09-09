from pydantic import BaseModel


class SimpleBet(BaseModel):
    direction: bool
    size: float
