import time
from unittest import mock

import pytest

from cachet import decorator_constructor
from cachet import dict_cache
from cachet import GenericCache
from cachet import io_cache
from cachet import sqlite_cache


def add_one_function(number):
    return number + 1


def non_deterministic_function(seed):
    return time.time()


class SomeClass:
    def add_one_method(self, number):
        return add_one_function(number)

    @staticmethod
    def add_one_staticmethod(number):
        return add_one_function(number)

    @classmethod
    def add_one_classmethod(cls, number):
        return add_one_function(number)


TEST_CACHES = (
    dict_cache,
    io_cache,
    sqlite_cache,
)
TEST_FUNCTIONS = (
    add_one_function,
    SomeClass().add_one_method,
    SomeClass().add_one_staticmethod,
    SomeClass().add_one_classmethod,
)


class TestGenericCache:
    def test_salt(self):
        cacher = decorator_constructor(GenericCache)

        function = mock.Mock(autospec=True)
        function.__doc__ = ""
        function.__qualname__ = ""
        cache = cacher(function)

        assert cache.__cache__._salt == b"04c238b7df3e8d88"


class TestCaches:
    @staticmethod
    def check_info(f, **fields):
        info = f.__cache__.info()
        for key, value in fields.items():
            assert info[key] == value

    @pytest.mark.parametrize("cache", TEST_CACHES)
    @pytest.mark.parametrize("function", TEST_FUNCTIONS)
    def test_basic_caching_occurs(self, tmpdir, cache, function):
        cached = cache(tmpdir=tmpdir.strpath)(function)
        self.check_info(cached, expires=0, hits=0, misses=0, size=0)

        assert cached(1) == 2
        self.check_info(cached, expires=0, hits=0, misses=1, size=1)

        assert cached(1) == 2
        self.check_info(cached, expires=0, hits=1, misses=1, size=1)

        assert cached(1) == 2
        self.check_info(cached, expires=0, hits=2, misses=1, size=1)

        assert cached(2) == 3
        self.check_info(cached, expires=0, hits=2, misses=2, size=2)

        assert cached(2) == 3
        self.check_info(cached, expires=0, hits=3, misses=2, size=2)

        assert cached(3) == 4
        self.check_info(cached, expires=0, hits=3, misses=3, size=3)

        cached.__cache__.bust()

    @pytest.mark.parametrize("cache", TEST_CACHES)
    @pytest.mark.parametrize("function", TEST_FUNCTIONS)
    def test_zero_ttl_only_expires(self, tmpdir, cache, function):
        cached = cache(tmpdir=tmpdir.strpath, ttl=0)(function)
        self.check_info(cached, expires=0, hits=0, misses=0, size=0)

        assert cached(1) == 2
        self.check_info(cached, expires=0, hits=0, misses=1, size=1)

        assert cached(1) == 2
        self.check_info(cached, expires=1, hits=0, misses=1, size=1)

        assert cached(1) == 2
        self.check_info(cached, expires=2, hits=0, misses=1, size=1)

        cached.__cache__.bust()

    @pytest.mark.parametrize("cache", TEST_CACHES)
    @pytest.mark.parametrize("function", TEST_FUNCTIONS)
    def test_dunders_work_as_expected(self, tmpdir, cache, function):
        cached = cache(tmpdir=tmpdir.strpath)(function)
        self.check_info(cached, expires=0, hits=0, misses=0, size=0)
        assert len(cached.__cache__) == 0

        assert cached(1) == 2
        self.check_info(cached, expires=0, hits=0, misses=1, size=1)
        assert len(cached.__cache__) == 1

        iter_cache = iter(cached.__cache__)
        key, _ = next(iter_cache)
        with pytest.raises(StopIteration):
            next(iter_cache)
        assert 1 in cached.__cache__
        self.check_info(cached, expires=0, hits=1, misses=1, size=1)
        del cached.__cache__[key]
        assert 1 not in cached.__cache__
        self.check_info(cached, expires=0, hits=1, misses=2, size=0)
        assert len(cached.__cache__) == 0

        cached.__cache__.bust()

    @pytest.mark.parametrize("cache", TEST_CACHES)
    def test_non_deterministic_caching_works_as_expected(self, tmpdir, cache):
        function = non_deterministic_function
        output = function(seed=0)
        assert function(seed=0) != output

        cached = cache(tmpdir=tmpdir.strpath)(function)
        self.check_info(cached, expires=0, hits=0, misses=0, size=0)

        output = cached(seed=0)
        self.check_info(cached, expires=0, hits=0, misses=1, size=1)

        assert cached(seed=0) == output
        self.check_info(cached, expires=0, hits=1, misses=1, size=1)

        assert cached(seed=0) == output
        self.check_info(cached, expires=0, hits=2, misses=1, size=1)

        assert cached(seed=1) != output
        self.check_info(cached, expires=0, hits=2, misses=2, size=2)

        cached.__cache__.bust()

    @pytest.mark.parametrize("function", TEST_FUNCTIONS)
    def test_in_memory_sqllite_never_touches_tmpdir(self, tmpdir, function):
        cache = sqlite_cache
        cached = cache(tmpdir=tmpdir.strpath, in_memory=True)(function)

        self.check_info(cached, expires=0, hits=0, misses=0, size=0)

        assert cached(1) == 2
        self.check_info(cached, expires=0, hits=0, misses=1, size=1)
        assert len(tmpdir.listdir()) == 0

        cached.__cache__.bust()
