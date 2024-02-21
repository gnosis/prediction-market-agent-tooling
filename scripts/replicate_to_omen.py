import typer
from prediction_market_agent_tooling.benchmark.utils import (
    get_markets,
    MarketFilter,
    MarketSource,
)


def main(
    market_type: MarketSource,
) -> None:
    # TODO: Fetch by newest and finish the rest.
    markets = get_markets(100, market_type, filter_=MarketFilter.open)


if __name__ == "__main__":
    typer.run(main)
