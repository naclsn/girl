import json
from logging import getLogger
from pathlib import PurePath
from traceback import format_exception
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


class PacifierLike(Protocol):
    """TODO"""

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
    """Proxy to any external interaction.

    The idea behind this proxy object is to have every run associated
    with one. Any interaction the run makes with the outside world (say
    reading a file or making a web request) is intercepted and performed
    by this proxy. Transiting bytes can then be tracked and saved and
    the whole run can be inspected or even replayed exactly as it was
    at the time (regardless of external system changes).

    An instance of :class:`World` is automatically constructed and
    handed to handlers for actual events. However, it may also be
    constructed manually when needed. For example to replay a run
    (see also :meth:`girl.events.Handler.fake`)::

        id = 'GET /hi/{name}'  # @app.web.event('GET', '/hi/{name}')
        runid = 'some-prior-run'  # maybe with app.store.listruns
        async with World(app, id, TODO, runid=runid) as world:
            await handler.fake(world)  # note: no crafted payload

    For the meaning and use of the ``pacifier`` parameter, see
    :class:`PacifierLike`. It correspond to the protocol that the
    argument must implement.
    """

    __slots__ = ("app", "id", "runid", "_pacifier", "web", "file")

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
        """Proxies file system related accesses."""
        self.web = _WorldWebProxy(self)
        """Proxies web HTTP related accesses."""

    async def __aenter__(self):
        """Prepare run.

        See also :meth:`girl.store.Store.beginrun`.
        """
        await self.app.store.beginrun(self)
        return self

    def tag(self, *tags: str):
        """Add tags to the run.

        Tags must be of at most 40 characters (per default setting) and
        must not contain ASCII control codes (only space and above).
        This in particular includes characters like ``\\t \\n \\r``...
        Invalid tags are simply ignored.

        Tags are of course only added if the run is "real" (eg. not
        replaying a prior run).
        """
        if not self._pacifier:
            max = self.app.settings.get("tag_max_len", 40)
            for tag in tags:
                # 32 is ord(' '); all char before that are illegal -- see ascii(7)
                if len(tag) < max and all(32 <= ord(c) for c in tag):
                    self.app.store.tagrun(self, tag)
                else:
                    _logger.warning(f"ignored illegal tag: {tag!r} in {self!r}")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """Finalize run.

        See also :meth:`girl.store.Store.finishrun`.

        If the run was interrupted by an exception, the trace is stored
        as part of the run under the key ``*exception*``.
        """
        if self.web._inner is not None:
            await self.web._inner.close()

        if exc_value is not None:
            trace = "".join(format_exception(exc_value)).encode()
            self.app.store.store(self, "*exception*", trace)
            self.tag("exception", type(exc_value).__name__)

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
    """Used internally to carry a method's signature from one class to
    a corresponding method on a proxy class."""
    return lambda proxy: proxy


class _WorldWebProxy:
    """Proxies web HTTP related accesses (see :class:`World`).

    The underlying :class:`aiohttp.ClientSession` can be configured
    through :attr:`app.App.settings`. For example, this may be
    reasonable::

        app = App(
            ...,
            {
                ...,
                "world_web": {"raise_for_status": True},
            },
        )

    A single session is constructed lazily so as to not add overhead
    to runs not needing web access.
    """

    __slots__ = ("_world", "_inner")

    def __init__(self, world: World):
        self._world = world
        self._inner = None

    def _sess(self):
        """Directly retrieve the :class:`aiohttp.ClientSession`.

        This should normally not be necessary outside library code.
        """
        if self._inner is None:
            se = self._world.app.settings.get("world_web") or {}
            self._inner = aiohttp.ClientSession(**se)
        return self._inner

    @_proxies(aiohttp.ClientSession.request)
    async def request(self, method: ..., url: ..., **kwargs: ...):
        """Makes a simple untracked request and discard the result.

        This can be preferable for PUT/PATCH/.. when there is no need
        to store the result for later inspection/replay.
        """
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
        """Send an HTTP request, receive the result as bytes."""
        if self._world._pacifier:
            data = await self._world._pacifier.performing(
                self._world,
                self.request_bytes,
                method,
                url,
                **kwargs,
            )
            return b"" if data is None else await data

        # store url and params early (before the actual request)
        # so that it's in run data even if it raises
        params = json.dumps(kwargs).encode()
        self._world.app.store.store(self._world, f"{method} {url} *params*", params)

        async with self._sess().request(method, url, **kwargs) as r:
            data = await r.read()
        self._world.app.store.store(self._world, f"{method} {url}", data)
        return data

    @_proxies(aiohttp.ClientSession.request)
    async def request_text(self, method: ..., url: ..., **kwargs: ...):
        """Send an HTTP request, decode the result as text."""
        return (await self.request_bytes(method, url, **kwargs)).decode()

    @_proxies(aiohttp.ClientSession.request)
    async def request_json(self, method: ..., url: ..., **kwargs: ...):
        """Send an HTTP request, load the result as JSON."""
        return json.loads(await self.request_text(method, url, **kwargs))


class _WorldFileProxy:
    """Proxies file system related accesses (see :class:`World`).

    Internally uses :class:`file.Path`, see :meth:`__call__` for
    constructing one.
    """

    __slots__ = ("_world", "RunPath")

    def __init__(self, world: World):
        from .events import file  # circular import...

        self._world = world
        self.RunPath = type("RunPath", (file.Path,), {"_world": self._world})

    def __call__(self, *path_bits: str | PurePath):
        """Make a :class:`file.Path` associated with the run's world.

        Reads through the returned object will be properly tracked for
        future inspections or replays.
        """
        return self.RunPath(*path_bits)
