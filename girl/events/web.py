import asyncio
import inspect
import json as jsonn
from collections import defaultdict
from collections.abc import AsyncGenerator
from collections.abc import Awaitable
from logging import getLogger
from pathlib import Path as StdPath
from pathlib import PurePath
from typing import Callable
from typing import Literal
from typing import TypeVar

from aiohttp import web
from yarl import URL  # XXX: transitive dep

from .. import app
from ..world import World
from .base import Base
from .base import Handler

_logger = getLogger(__name__)

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


class Request:
    __slots__ = ("_world", "_req", "method", "rel_url", "match_info", "_head", "_body")

    def __init__(
        self,
        world: World,
        method: MethodStr,
        rel_url: URL,
        match_info: dict[str, str],
        head: dict[str, str],
        body: bytes,
        _req: web.Request | None,
    ):
        self._world = world
        self._req = _req
        self.method = method
        self.rel_url = rel_url
        self.match_info = match_info
        self._head = head
        self._body = body

    @property
    def body(self):
        return self._body

    @property
    def text(self):
        return self.body.decode()

    @property
    def json(self):
        return jsonn.loads(self.text)

    def header(self, name: str, default: str | None = None, /):
        return self._head.get(name.lower(), default)

    _MISSING = object()

    def respond(
        self,
        *,
        body: bytes | None = None,
        text: str | None = None,
        json: object = _MISSING,
        file: str | PurePath | None = None,
        status: int = 200,
        reason: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        if 1 != (
            (body is not None)
            + (text is not None)
            + (json is not Request._MISSING)
            + (file is not None)
        ):
            raise ValueError(
                "exactly one of 'body', 'text', 'json' or 'file' must be given"
            )

        if file is not None:
            return web.FileResponse(file)

        if json is not Request._MISSING:
            text = jsonn.dumps(json)
        if text is not None:
            body = text.encode()
        assert body

        return web.Response(body=body, status=status, reason=reason, headers=headers)

    @classmethod
    async def _from_aiohttp(cls, world: World, req: web.Request):
        headers = {k.lower(): v for k, v in req.headers.items()}
        body = await req.read()

        meth_url = f"{req.method} {req.rel_url}".encode("ascii")
        head = jsonn.dumps(headers).encode()
        match = jsonn.dumps(req.match_info).encode()
        world.app.store.store(world, "*request-url*", meth_url)
        world.app.store.store(world, "*request-match*", match)
        world.app.store.store(world, "*request-head*", head)
        world.app.store.store(world, "*request-body*", body)

        meth: ... = req.method  # cast str to literal
        return cls(world, meth, req.rel_url, req.match_info, headers, body, req)

    @classmethod
    def _from_storage(cls, world: World):
        meth_url = world.app.store.load(world, "*request-url*")
        match = world.app.store.load(world, "*request-match*")
        head = world.app.store.load(world, "*request-head*")
        body = world.app.store.load(world, "*request-body*")
        headers = jsonn.loads(head)
        match_info = jsonn.loads(match)
        meth, _, rel_url = meth_url.decode("ascii").partition(" ")

        meth: ... = meth  # cast str to literal
        return cls(world, meth, URL(rel_url), match_info, headers, body, None)

    @classmethod
    def _from_bytes(cls, world: World, payload: bytes):
        assert not "implemented", Request._from_bytes
        return cls(world, ...)


HttpHandler = (
    Callable[[World, Request], Awaitable[web.StreamResponse]]
    | Callable[[World, Request], AsyncGenerator[web.StreamResponse]]
)
_HttpHandler_ = TypeVar("_HttpHandler_", bound=HttpHandler)

_Bind = tuple[str, int] | PurePath


class EventsWeb(Base):
    def __init__(self, app: "app.App"):
        self._app = app
        self._handlers = dict[str, Handler[HttpHandler]]()

        self._apps = defaultdict[_Bind, web.Application](web.Application)

    def summary(self):
        txt = ""
        for bind, app in self._apps.items():
            txt += f"{'TCP' if isinstance(bind, tuple) else 'Unix'} site on {bind}:\n"
            for r in app.router.routes():
                path = "(no resource)" if r.resource is None else r.resource.canonical
                fn = getattr(r.handler, "__wrapped__")
                txt += f"    {r.method} {path} {fn}\n"
        return txt

    def event(self, bind: str | PurePath, method: MethodStr, path: str):
        """ """
        if isinstance(bind, str) and ":" in bind:
            host, _, port = bind.partition(":")
            bindd = ("127.0.0.1" if "localhost" == host else host, int(port))
        else:
            bindd = PurePath(StdPath(bind).resolve())

        id = f"{bind} {method} {path}"

        def adder(fn: _HttpHandler_):
            if id in self._handlers:
                raise ValueError("event already observed")

            ret_fn = fn  # HACK: circumvent type narrowing being dum

            if inspect.isasyncgenfunction(fn):

                async def wrapper(req: web.Request):
                    world = await World(self._app, id, None).__aenter__()
                    _logger.debug(f"Web event with {world!r} (generator - will resume)")
                    reqq = await Request._from_aiohttp(world, req)
                    gen = fn(world, reqq)
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

                async def wrapper(req: web.Request):
                    async with World(self._app, id, None) as world:
                        _logger.debug(f"Web event with {world!r}")
                        reqq = await Request._from_aiohttp(world, req)
                        res: web.Response = await fn(world, reqq)
                        return res

            else:
                raise TypeError("handler should be async def with optionally a yield")

            setattr(wrapper, "__wrapped__", ret_fn)
            self._apps[bindd].router.add_route(method, path, wrapper)
            self._handlers[id] = Handler(id, fn, EventsWeb._fake)
            return ret_fn

        return adder

    def handlers(self):
        return set(self._handlers)

    def handler(self, id: str):
        return self._handlers[id]

    @staticmethod
    async def _fake(world: World, payload: bytes | None, fn: HttpHandler):
        if payload is None:
            assert world._pacifier and not world._pacifier.is_new
            req = Request._from_storage(world)
        else:
            req = Request._from_bytes(world, payload)

        if inspect.isasyncgenfunction(fn):
            gen = fn(world, req)
            res: web.Response = await anext(gen)
            await anext(gen, None)
            return res

        elif inspect.iscoroutinefunction(fn):
            return await fn(world, req)

        assert not "reachable"

    @staticmethod
    async def _resume_in_background(gen: AsyncGenerator[object], world: World):
        _logger.debug(f"{world!r} resuming in the background")
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
                site_log = f"TCP site on {bind}:"
                await web.TCPSite(runn, *bind).start()
            else:
                site_log = f"Unix site on {bind}:"
                await web.UnixSite(runn, str(bind)).start()

            _logger.info(site_log)
            for r in app.router.routes():
                path = "(no resource)" if r.resource is None else r.resource.canonical
                fn = getattr(r.handler, "__wrapped__")
                _logger.info(f"    {r.method} {path} {fn}")

            return runn

        self._runners = await asyncio.gather(*(_serv(*p) for p in self._apps.items()))

    async def __aexit__(self, *_):
        await asyncio.gather(*(runn.cleanup() for runn in self._runners))
