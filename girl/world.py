import json
from pathlib import PurePath
from types import TracebackType
from typing import Callable
from typing import Concatenate
from typing import ParamSpec
from typing import TypeVar

import aiohttp
from coolname import generate_slug

from . import app


class World:
    """ """

    __slots__ = (
        "app",
        "id",
        "runid",
        "_counter",
        "_pacifier",
        "web",
        "file",
        "share",
    )

    def __init__(self, app: "app.App", id: str, pacifier: bool, *, runid: str = ""):
        self.app = app

        self.id = id
        self.runid = runid or generate_slug(3)
        self._counter = 0
        self._pacifier = pacifier

        self.file = _WorldFileProxy(self)
        self.share = ...  # set[tuple[str, ...]]  # wrapped as to be write-once
        self.web = _WorldWebProxy(self)

    async def __aenter__(self):
        await self.app.store.beginrun(self)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        await self.web._inner.close()
        await self.app.store.finishrun(self)


_Params_ = ParamSpec("_Params_")
_RetInner_ = TypeVar("_RetInner_")
_RetProxy_ = TypeVar("_RetProxy_")
_SelfInner_ = TypeVar("_SelfInner_")
_SelfProxy_ = TypeVar("_SelfProxy_")


def _proxies(
    _proxied: Callable[Concatenate[_SelfInner_, _Params_], _RetInner_],
) -> Callable[
    [Callable[Concatenate[_SelfProxy_, _Params_], _RetProxy_]],
    Callable[Concatenate[_SelfProxy_, _Params_], _RetProxy_],
]:
    return lambda proxy: proxy


class _WorldWebProxy:
    __slots__ = ("_world", "_inner")

    def __init__(self, world: World):
        self._world = world
        if not self._world._pacifier:
            self._inner = aiohttp.ClientSession()

    @_proxies(aiohttp.ClientSession.request)
    def request_untracked(self, method: ..., url: ..., **kwargs: ...):
        return self._inner.request(method, url, **kwargs)

    @_proxies(aiohttp.ClientSession.request)
    async def request_bytes(self, method: ..., url: ..., **kwargs: ...):
        if self._world._pacifier:
            key = f"{method} {url}"
            assert not "done", key
            return bytes()

        async with self._inner.request(method, url, **kwargs) as r:
            r = await r.read()
        # self._world._trackorsomethingidkk(key, r, kwargs)
        return r

    @_proxies(aiohttp.ClientSession.request)
    async def request_text(self, method: ..., url: ..., **kwargs: ...):
        return (await self.request_bytes(method, url, **kwargs)).decode()

    @_proxies(aiohttp.ClientSession.request)
    async def request_json(self, method: ..., url: ..., **kwargs: ...):
        return json.loads(await self.request_text(method, url, **kwargs))


class _WorldFileProxy:
    __slots__ = ("_world", "RunPath")

    def __init__(self, world: World):
        from .events import file  # circular import...

        self._world = world
        self.RunPath = type("RunPath", (file.Path,), {"_world": self._world})

    def __call__(self, *path_bits: str | PurePath):
        return self.RunPath(*path_bits)
