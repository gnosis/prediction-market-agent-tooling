import hishel


class HttpxCachedClient:
    def __init__(self):
        storage = hishel.FileStorage(ttl=3600, check_ttl_every=600)
        controller = hishel.Controller(force_cache=True)
        self.client = hishel.CacheClient(storage=storage, controller=controller)

    def get_client(self):
        return self.client
