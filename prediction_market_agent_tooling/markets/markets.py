from enum import Enum


class MarketType(str, Enum):
    MANIFOLD = "manifold"
    OMEN = "omen"
    POLYMARKET = "polymarket"
