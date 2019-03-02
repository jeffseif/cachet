class CacheMissException(Exception):
    pass


class DontCacheException(Exception):
    pass


class ExpiredKeyException(Exception):
    pass
