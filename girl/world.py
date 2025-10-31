import json
from logging import getLogger
from pathlib import PurePath
from types import TracebackType
from typing import Callable
from typing import Concatenate
from typing import ParamSpec
from typing import Protocol
from typing import TypeVar

import aiohttp
from coolname import generate_slug

from . import app

_logger = getLogger(__name__)


class PacifierLike(Protocol):  # xxx: for now a protocol, maybe later an ABC
    @property
    def is_new(self) -> bool:
        """ """
        ...

    def storing(self, world: "World", key: str, ts: float, data: bytes):
        """ """
        ...

    def loading(self, world: "World", key: str, ts: float, data: bytes) -> bytes:
        """ """
        ...

    def performing(
        self,
        world: "World",
        fn: Callable[..., object],
        *args: ...,
        **kwargs: ...,
    ) -> ...:
        """if returns None then call site gets to decide on sane default"""
        ...


class World:
    """ """

    __slots__ = (
        "app",
        "id",
        "runid",
        "_pacifier",
        "web",
        "file",
        # "share",
    )

    def __init__(
        self,
        app: "app.App",
        id: str,
        pacifier: PacifierLike | None,
        *,
        runid: str | None = None,
    ):
        self.app = app

        self.id = id
        self.runid = runid or generate_slug(app.settings.get("slug_pattern"))
        self._pacifier = pacifier

        self.file = _WorldFileProxy(self)
        self.web = _WorldWebProxy(self)

    async def __aenter__(self):
        await self.app.store.beginrun(self)
        return self

    def tag(self, *tags: str):
        """add a tag to the run"""
        if not self._pacifier:
            for tag in tags:
                # 32 is ord(' '); all char before that are illegal -- see ascii(7)
                if len(tag) < 30 and all(32 <= ord(c) for c in tag):
                    self.app.store.tagrun(self, tag)
                else:
                    _logger.warning(f"ignored illegal tag: {tag!r} in {self!r}")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        if self.web._inner is not None:
            await self.web._inner.close()
        await self.app.store.finishrun(self)

    def __repr__(self):
        return f"<world {self.id!r} {self.runid!r}>"


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
        self._inner = None

    def _sess(self):
        if self._inner is None:
            se = self._world.app.settings.get("world_web") or {}
            self._inner = aiohttp.ClientSession(**se)
        return self._inner

    @_proxies(aiohttp.ClientSession.request)
    async def request(self, method: ..., url: ..., **kwargs: ...):
        """not tracked"""
        if self._world._pacifier:
            await self._world._pacifier.performing(
                self._world,
                self.request,
                method,
                url,
                **kwargs,
            )
        else:
            (await self._sess().request(method, url, **kwargs)).close()

    @_proxies(aiohttp.ClientSession.request)
    async def request_bytes(self, method: ..., url: ..., **kwargs: ...) -> bytes:
        if self._world._pacifier:
            data = await self._world._pacifier.performing(
                self._world,
                self.request_bytes,
                method,
                url,
                **kwargs,
            )
            return b"" if data is None else await data

        async with self._sess().request(method, url, **kwargs) as r:
            data = await r.read()

        params = json.dumps(kwargs).encode()
        self._world.app.store.store(self._world, f"{method} {url} *params*", params)
        self._world.app.store.store(self._world, f"{method} {url}", data)

        return data

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
