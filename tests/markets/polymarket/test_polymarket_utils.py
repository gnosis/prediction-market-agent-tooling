import pytest

from prediction_market_agent_tooling.markets.polymarket.utils import (
    PolymarketFullMarket,
    Resolution,
    find_resolution_on_polymarket,
    find_url_to_polymarket,
)


@pytest.mark.parametrize(
    "question, expected",
    [
        (
            "Presidential Election Winner 2024",
            "https://polymarket.com/event/presidential-election-winner-2024",
        )
    ],
)
def test_find_url_to_polymarket(question: str, expected: str) -> None:
    assert find_url_to_polymarket(question) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://polymarket.com/event/presidential-election-winner-2024",
            False,
        ),
        (
            "https://polymarket.com/event/will-trump-make-bond-by-march-25/will-trump-make-bond-by-march-25",
            True,
        ),
    ],
)
def test_polymarket_is_main(url: str, expected: bool) -> None:
    full_market = PolymarketFullMarket.fetch_from_url(url)
    assert full_market is not None
    assert full_market.is_main_market == expected


@pytest.mark.parametrize(
    "question, expected",
    [
        (
            # Should break after March 25, simply use the correct resolution afterwards.
            "Will Trump make bond by March 25?",
            None,
        ),
        (
            "Will Putin be reelected?",
            Resolution.YES,
        ),
    ],
)
def test_polymarket_find_resolution(question: str, expected: Resolution | None) -> None:
    assert find_resolution_on_polymarket(question) == expected
