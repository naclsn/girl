import aiohttp
from pathlib import Path as StdPath
from pathlib import PurePath
from sys import version_info
from typing import Callable
from typing import Concatenate
from typing import ParamSpec
from typing import TypeVar


class World:
    """ """

    __slots__ = ("id", "web", "file", "share")

    def __init__(self, id: str):
        self.id = id
        self.web = _WorldWebProxy(aiohttp.ClientSession())
        self.file = _WorldFileProxy()
        self.share = ...  # set[tuple[str, ...]]  # wrapped as to be write-once

    async def _close(self):
        await self.web._inner.close()


Params = ParamSpec("Params")
Ret = TypeVar("Ret")
SelfInner = TypeVar("SelfInner")
SelfProxy = TypeVar("SelfProxy")


def _proxies(_wrapped: Callable[Concatenate[SelfInner, Params], Ret]) -> Callable[
    [Callable[Concatenate[SelfProxy, Params], Ret]],
    Callable[Concatenate[SelfInner, Params], Ret],
]:
    return lambda proxy: proxy


class _WorldWebProxy:
    def __init__(self, inner: aiohttp.ClientSession):
        self._inner = inner

    @_proxies(aiohttp.ClientSession.request)
    def request(self, method, url, **kwargs):
        return self._inner.request(method, url, **kwargs)


class Path(StdPath):
    def read_text(self, encoding=None, errors=None, newline=None):
        if (3, 13) < version_info:
            return super().read_text(encoding, errors, newline)
        return super().read_text(encoding, errors)

    def rename(self, target):
        return super().rename(target)


class _WorldFileProxy:
    def __call__(self, *path_bits: str | PurePath):
        return Path(*path_bits)
