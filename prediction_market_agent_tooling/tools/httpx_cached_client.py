import hishel


class HttpxCachedClient:
    def __init__(self) -> None:
        storage = hishel.FileStorage(
            ttl=24 * 60 * 60,
            check_ttl_every=1 * 60 * 60,
        )
        controller = hishel.Controller(force_cache=True)
        self.client = hishel.CacheClient(storage=storage, controller=controller)

    def get_client(self) -> hishel.CacheClient:
        return self.client
