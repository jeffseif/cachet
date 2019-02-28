import functools
import glob
import gzip
import hashlib
import inspect
import os
import pickle
import sqlite3
import time


DEFAULT_DIR = '/tmp'
DEFAULT_TTL = 24 * 60 * 60


class CacheMissException(Exception):
    pass


class DontCacheException(Exception):
    pass


class ExpiredKeyException(Exception):
    pass


class GenericCache:

    _salt = b''
    _expires = _hits = _misses = 0

    def __init__(self, function, ttl=DEFAULT_TTL, tmpdir=DEFAULT_DIR):
        self.ttl = ttl
        self.tmpdir = tmpdir
        module = inspect.getmodule(function)
        _salt = self.args_to_key(
            module=module.__name__ if module is not None else '',
            qualname=function.__qualname__,
        )
        self._salt = bytes(_salt, 'utf8')

    def __contains__(self, *args):
        try:
            self[self.args_to_key(*args)]
            return True
        except (CacheMissException, ExpiredKeyException):
            return False

    def __getitem(self, key):
        raise NotImplementedError

    def __getitem__(self, key):
        try:
            value = self._getitem(key)
            self._hits += 1
            return value
        except CacheMissException as e:
            self._misses += 1
            raise e
        except ExpiredKeyException as e:
            self._expires += 1
            raise e

    @functools.lru_cache(maxsize=None)
    def args_to_key(self, *args, **kwargs):
        return hashlib.blake2b(
            pickle.dumps((args, kwargs)),
            digest_size=8,
            salt=self._salt,
        ).hexdigest()

    def bust(self):
        for k, v in list(self):
            del self[k]

    def info(self):
        return {
            'expires': self._expires,
            'hits': self._hits,
            'misses': self._misses,
            'salt': self._salt,
            'size': len(self),
        }

    @property
    def expiration(self):
        return self.now + self.ttl

    @property
    def now(self):
        return time.time()


class DictCache(GenericCache):

    kv = {}

    def __delitem__(self, key):
        del self.kv[key]

    def _getitem(self, key):
        if key not in self.kv:
            raise CacheMissException

        value, expiration = self.kv[key]
        if expiration < self.now:
            raise ExpiredKeyException

        return pickle.loads(value)

    def __iter__(self):
        for key, (value, _) in self.kv.items():
            yield key, pickle.loads(value)

    def __len__(self):
        return len(self.kv)

    def __setitem__(self, key, value):
        self.kv[key] = (pickle.dumps(value), self.expiration)


class IOCache(GenericCache):

    @functools.lru_cache(maxsize=None)
    def key_to_filename(self, key):
        return '/'.join((
            self.tmpdir,
            '.'.join(('', 'cache', key, 'gz')),
        ))

    def __delitem__(self, filename):
        os.remove(filename)

    def _getitem(self, key):
        filename = self.key_to_filename(key)
        if not os.path.isfile(filename):
            raise CacheMissException

        with gzip.open(filename, 'rb') as f:
            value, expiration = pickle.load(f)

        if expiration < self.now:
            raise ExpiredKeyException

        return value

    def __iter__(self):
        for filename in glob.glob('/'.join((self.tmpdir, '.cache.*.gz'))):
            with gzip.open(filename, 'rb') as f:
                value, _ = pickle.load(f)
                yield filename, value

    def __len__(self):
        return len(glob.glob('/'.join((self.tmpdir, '.cache.*.gz'))))

    def __setitem__(self, key, value):
        filename = self.key_to_filename(key)
        with gzip.open(filename, 'wb') as f:
            pickle.dump((value, self.expiration), f)


class SqliteCache(GenericCache):

    filename = '.cache.sqlite'

    CONTAINS_SQL = 'SELECT COUNT(*) FROM kv WHERE (k = ?) AND (e > ?) ;'
    CREATE_SQL = 'CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v BLOB, e FLOAT) ;'
    DEL_SQL = 'DELETE FROM kv WHERE (k = ?) ;'
    GET_SQL = 'SELECT v, e FROM kv WHERE (k = ?) ;'
    ITER_SQL = 'SELECT k, v FROM kv ;'
    LEN_SQL = 'SELECT COUNT(*) FROM kv ;'
    SET_SQL = 'INSERT OR REPLACE INTO kv (k, v, e) VALUES (?, ?, ?) ;'

    def __init__(self, *args, **kwargs):
        in_memory = kwargs.pop('in_memory', False)
        super().__init__(*args, **kwargs)
        db_path = ':memory:' if in_memory else '/'.join((self.tmpdir, self.filename))
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(self.CREATE_SQL)
        self.conn.commit()

    def select_query(self, sql, *args):
        with self.conn as c:
            yield from c.execute(sql, args)

    def __delitem__(self, key):
        with self.conn as c:
            c.execute(self.DEL_SQL, (key, ))

    def _getitem(self, key):
        try:
            value, expiration = next(self.select_query(self.GET_SQL, key))
            if expiration < self.now:
                raise ExpiredKeyException
            return pickle.loads(value)
        except StopIteration:
            raise CacheMissException

    def __iter__(self):
        for key, value in self.select_query(self.ITER_SQL):
            yield key, pickle.loads(value)

    def __len__(self):
        length, =  next(self.select_query(self.LEN_SQL))
        return length

    def __setitem__(self, key, value):
        with self.conn as c:
            c.execute(self.SET_SQL, (key, pickle.dumps(value), self.expiration))


def decorator_constructor(cache_class, **outer_kwargs):

    def decorator(function):

        @functools.wraps(function)
        def returned(*args, **kwargs):
            key = the_cache.args_to_key(*args, **kwargs)

            try:
                result = the_cache[key]
            except (CacheMissException, ExpiredKeyException):
                try:
                    result = function(*args, **kwargs)
                    the_cache[key] = result
                except DontCacheException as e:
                    print(e)
                    result = None
            return result

        returned.__cache__ = the_cache = cache_class(function, **outer_kwargs)

        return returned

    return decorator


dict_cache = functools.partial(decorator_constructor, DictCache)
io_cache = functools.partial(decorator_constructor, IOCache)
sqlite_cache = functools.partial(decorator_constructor, SqliteCache)
