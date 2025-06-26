import hishel
import httpx

from prediction_market_agent_tooling.tools.singleton import SingletonMeta

ONE_DAY_IN_SECONDS = 60 * 60 * 24


class HttpxCachedClient(metaclass=SingletonMeta):
    def __init__(self, ttl: int = ONE_DAY_IN_SECONDS) -> None:
        storage = hishel.FileStorage(
            ttl=ttl,
            check_ttl_every=60,
        )
        controller = hishel.Controller(force_cache=True)
        self.client: httpx.Client = hishel.CacheClient(
            storage=storage, controller=controller
        )

    def get_client(self) -> httpx.Client:
        return self.client
