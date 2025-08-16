import json
from pathlib import Path as StdPath
from pathlib import PurePath
from types import TracebackType
from typing import Callable
from typing import Concatenate
from typing import ParamSpec
from typing import TypeVar

import aiohttp


class World:
    """ """

    __slots__ = ("id", "_pacifier", "web", "file", "share")

    def __init__(self, id: str, pacifier: bool):
        self.id = id
        self._pacifier = pacifier
        self.web = _WorldWebProxy(self)
        self.file = _WorldFileProxy(self)
        self.share = ...  # set[tuple[str, ...]]  # wrapped as to be write-once

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        await self.web._inner.close()


Params = ParamSpec("Params")
RetInner = TypeVar("RetInner")
RetProxy = TypeVar("RetProxy")
SelfInner = TypeVar("SelfInner")
SelfProxy = TypeVar("SelfProxy")


def _proxies(_proxied: Callable[Concatenate[SelfInner, Params], RetInner]) -> Callable[
    [Callable[Concatenate[SelfProxy, Params], RetProxy]],
    Callable[Concatenate[SelfProxy, Params], RetProxy],
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


# pathlib being trash in py 3.10, see https://stackoverflow.com/a/61689743
class Path(type(StdPath())):
    """

    only the following accesses are tracked:
        * :meth:`read_bytes`
        * :meth:`read_text`
        * :meth:`read_json`
        * :meth:`write_bytes`
        * :meth:`write_text`
        * :meth:`write_json`
    """

    __slots__ = ("_world",)
    _world: World

    def read_bytes(self):
        _w: World | None = getattr(self, "_world", None)
        if _w and _w._pacifier:
            key = str(self.resolve())
            assert not "done", key
            return bytes()

        r = super().read_bytes()
        # self._world._trackorsomethingidkk(key, r)
        return r

    def write_bytes(self, data: bytes):
        _w: World | None = getattr(self, "_world", None)
        if _w and _w._pacifier:
            key = str(self.resolve())
            assert not "done", key
            return int()

        # self._world._trackorsomethingidkk(key, data)
        return super().write_bytes(data)

    def read_text(self):
        return self.read_bytes().decode()

    def write_text(self, data: str):
        return self.write_bytes(data.encode())

    def read_json(self):
        return json.loads(self.read_text())

    def write_json(self, data: ...):
        return self.write_text(json.dumps(data))


class _WorldFileProxy:
    __slots__ = ("_world",)

    def __init__(self, world: World):
        self._world = world

    def __call__(self, *path_bits: str | PurePath):
        r = Path(*path_bits)
        r._world = self._world
        return r
