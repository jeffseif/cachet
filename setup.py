from setuptools import setup

from cachet import __author__
from cachet import __email__
from cachet import __program__
from cachet import __url__
from cachet import __version__


setup(
    author=__author__,
    author_email=__email__,
    install_requires=[],
    name=__program__,
    packages=[__program__],
    platforms='all',
    setup_requires=[
        'setuptools',
        'tox',
    ],
    test_suite='tests',
    url=__url__,
    version=__version__,
)
