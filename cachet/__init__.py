import functools
import glob
import gzip
import hashlib
import inspect
import os
import pickle
import sqlite3
import time


class CacheMissException(Exception):
    pass


class DontCacheException(Exception):
    pass


class ExpiredKeyException(Exception):
    pass


class GenericCache:

    def __init__(self, function, ttl):
        self.ttl = ttl
        module = inspect.getmodule(function)
        self.args_prefix = (
            module.__name__ if module is not None else None,
            function.__qualname__,
        )

    def __contains__(self, args):
        try:
            self[self.args_to_key(*args)]
            return True
        except (CacheMissException, ExpiredKeyException) as e:
            return False

    @functools.lru_cache(maxsize=None)
    def args_to_key(self, *args, **kwargs):
        pickle_string = pickle.dumps((self.args_prefix, args, kwargs))
        return hashlib.md5(pickle_string).hexdigest()

    def bust(self):
        for k, v in list(self):
            del self[k]

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

    def __getitem__(self, key):
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

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def key_to_filename(key):
        return '.'.join(('', 'cache', key, 'gz'))

    def __delitem__(self, filename):
        os.remove(filename)

    def __getitem__(self, key):
        filename = self.key_to_filename(key)
        if not os.path.isfile(filename):
            raise CacheMissException

        with gzip.open(filename, 'rb') as f:
            value, expiration = pickle.load(f)

        if expiration < self.now:
            raise ExpiredKeyException

        return value

    def __iter__(self):
        for filename in glob.glob('./.cache.*.gz'):
            with gzip.open(filename, 'rb') as f:
                value, _ = pickle.load(f)
                yield filename, value

    def __len__(self):
        return len(glob.glob('./.cache.*.gz'))

    def __setitem__(self, key, value):
        filename = self.key_to_filename(key)
        with gzip.open(filename, 'wb') as f:
            pickle.dump((value, self.expiration), f)


class SqliteCache(GenericCache):

    DEFAULT_FILENAME = '.cache.sqlite'

    CONTAINS_SQL = 'SELECT COUNT(*) FROM kv WHERE (k = ?) AND (e > ?) ;'
    CREATE_SQL = 'CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v BLOB, e FLOAT) ;'
    DEL_SQL = 'DELETE FROM kv WHERE (k = ?) ;'
    GET_SQL = 'SELECT v, e FROM kv WHERE (k = ?) ;'
    ITER_SQL = 'SELECT k, v FROM kv ;'
    LEN_SQL = 'SELECT COUNT(*) FROM kv ;'
    SET_SQL = 'INSERT OR REPLACE INTO kv (k, v, e) VALUES (?, ?, ?) ;'

    def __init__(self, *args, **kwargs):
        filename = kwargs.pop('filename', self.DEFAULT_FILENAME)
        super().__init__(*args, **kwargs)
        self.conn = sqlite3.connect(filename)
        self.conn.execute(self.CREATE_SQL)
        self.conn.commit()

    def select_query(self, sql, *args):
        with self.conn as c:
            yield from c.execute(sql, args)

    def __delitem__(self, key):
        with self.conn as c:
            c.execute(self.DEL_SQL, (key, ))

    def __getitem__(self, key):
        try:
            value, expiration = next(self.select_query(self.GET_SQL, key))
            if expiration < self.now:
                raise ExpiredKeyException
            return pickle.loads(value)
        except StopIteration as e:
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


def cache_decorator(cache_class, ttl, **kwargs):

    def decorator(function):

        def returned(*args, **kwargs):
            key = the_cache.args_to_key(*args, **kwargs)

            try:
                result = the_cache[key]
            except (CacheMissException, ExpiredKeyException) as e:
                try:
                    result = function(*args, **kwargs)
                    the_cache[key] = result
                except DontCacheException as e:
                    print(e)
                    result = None
            return result

        returned.__cache__ = the_cache = cache_class(function, ttl, **kwargs)

        return returned

    return decorator


dict_cache = functools.partial(cache_decorator, DictCache)
io_cache = functools.partial(cache_decorator, IOCache)
sqlite_cache = functools.partial(cache_decorator, SqliteCache)


COUNT = 0
@sqlite_cache(ttl=1, filename=':memory:')
def count():
    global COUNT
    COUNT += 1
    return COUNT

for _ in range(5):
    print(count())
    time.sleep(0.5)

print(len(count.__cache__), list(count.__cache__))
count.__cache__.bust()
print(len(count.__cache__))

@sqlite_cache(ttl=1)
def count2():
    print('jeff')

for _ in range(5):
    print(count2())
    time.sleep(0.5)

print(len(count2.__cache__), list(count2.__cache__))

@sqlite_cache(ttl=1)
def count3():
    print('seif')

for _ in range(5):
    print(count3())
    time.sleep(0.5)

print(len(count3.__cache__), list(count3.__cache__))

class Person:
    def __init__(self, age):
        self.age = age

    @dict_cache(ttl=1)
    def add_year(self):
        self.age += 1
        return self.age

person = Person(age=5)
for _ in range(5):
    print(person.add_year())
    time.sleep(0.5)
