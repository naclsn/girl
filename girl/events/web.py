import asyncio
import inspect
from collections import defaultdict
from collections.abc import AsyncGenerator
from collections.abc import Awaitable
from functools import wraps
from logging import getLogger
from pathlib import Path as StdPath
from pathlib import PurePath
from typing import Callable
from typing import Literal

from aiohttp import web

from .base import Base
from ..world import World

MethodStr = Literal[
    "*",
    "CONNECT",
    "HEAD",
    "GET",
    "DELETE",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
    "TRACE",
]

HttpHandler = (
    Callable[[World, web.Request], Awaitable[web.StreamResponse]]
    | Callable[[World, web.Request], AsyncGenerator[web.StreamResponse]]
)

_Bind = tuple[str, int] | PurePath

_logger = getLogger(__name__)


class EventsWeb(Base):
    def __init__(self):
        self._apps = defaultdict[_Bind, web.Application](web.Application)
        self._ids = set[str]()

    def event(self, bind: str | PurePath, method: MethodStr, path: str):
        """ """
        if isinstance(bind, str) and ":" in bind:
            host, _, port = bind.partition(":")
            bindd = ("127.0.0.1" if "localhost" == host else host, int(port))
        else:
            bindd = PurePath(StdPath(bind).resolve())

        id = f"{bind} {method} {path}"

        def adder(fn: HttpHandler):
            if id in self._ids:
                raise ValueError("event already observed")

            ret_fn = fn  # HACK: circumvent type narrowing being dum

            if inspect.isasyncgenfunction(fn):

                @wraps(fn)
                async def wrapper(req: web.Request):
                    world = await World(id).__aenter__()
                    gen = fn(world, req)
                    try:
                        res: web.Response = await anext(gen)
                    except BaseException as e:
                        await world.__aexit__(type(e), e, e.__traceback__)
                        raise
                    # may resume in the background after early response,
                    # the session's world handle is kept live until then;
                    t = asyncio.create_task(EventsWeb._resume_in_background(gen, world))
                    # `fut.result` will re-raise if there was an exception
                    t.add_done_callback(lambda fut: fut.result())
                    return res

            elif inspect.iscoroutinefunction(fn):

                @wraps(fn)
                async def wrapper(req: web.Request):
                    async with World(id) as world:
                        res: web.Response = await fn(world, req)
                        return res

            else:
                raise TypeError("handler should be async def with optionally a yield")

            self._apps[bindd].router.add_route(method, path, wrapper)
            self._ids.add(id)
            return ret_fn

        return adder

    @staticmethod
    async def _resume_in_background(gen: AsyncGenerator[object], world: World):
        try:
            await anext(gen, None)
        except BaseException as e:
            await world.__aexit__(type(e), e, e.__traceback__)
            raise
        await world.__aexit__()

    async def __aenter__(self):
        async def _serv(bind: _Bind, app: web.Application):
            runn = web.AppRunner(app)
            await runn.setup()

            if isinstance(bind, tuple):
                site_log = f"TCP site on {bind}"
                await web.TCPSite(runn, *bind).start()
            else:
                site_log = f"Unix site on {bind}"
                await web.UnixSite(runn, str(bind)).start()

            _logger.info(site_log)
            for r in app.router.routes():
                path = "(no resource)" if r.resource is None else r.resource.canonical
                _logger.info(f"    {r.method} {path}")

            return runn

        self._runners = await asyncio.gather(*(_serv(*p) for p in self._apps.items()))

    async def __aexit__(self, *_):
        await asyncio.gather(*(runn.cleanup() for runn in self._runners))
