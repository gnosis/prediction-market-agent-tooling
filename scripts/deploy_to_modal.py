import typer
from modal import App, Period

from deploy.agent_example import DeployableCoinFlipAgent
from markets.markets import MarketType


def main() -> None:
    app = App(name="coin-flip-agent")

    @app.function(schedule=Period(minutes=5))
    def execute_remote():
        print("hello")

    DeployableCoinFlipAgent(place_bet=False).deploy_to_modal(
        market_type=MarketType.OMEN, cron_schedule="*/5 * * * *", app=app
    )


if __name__ == "__main__":
    typer.run(main)
