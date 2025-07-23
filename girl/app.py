import asyncio
import inspect
from collections import defaultdict
from fnmatch import fnmatch
from logging import getLogger
from pathlib import Path as StdPath
from pathlib import PurePath
from typing import Callable
from typing import TypeVar
from typing import TypeVarTuple

from aiohttp import web
from asyncinotify import Inotify
from asyncinotify import Mask
from asyncinotify import Watch

from .typedefs import FileHandler
from .typedefs import Handlers
from .typedefs import HttpHandler
from .typedefs import MethodStr
from .world import Path
from .world import World

_Ret_ = TypeVar("_Ret_")
_Params_ = TypeVarTuple("_Params_")
_Fn_ = TypeVar("_Fn_", bound=Handlers)
_Bind = tuple[str, int] | PurePath
_Id = str
_FileCbInfo = tuple[str, _Id, FileHandler]


def _reload_guard(
    id: _Id,
) -> Callable[[Callable[[_Fn_], _Fn_]], Callable[[_Fn_], _Fn_]]:
    """idea: only call function if not reloading or reloading this one"""
    if True or id is ladida:
        return lambda adder: adder
    return lambda adder: lambda fn: fn


class App:
    """ """

    __slots__ = (
        "_aiohttp_apps",
        "_aiohttp_ids",
        "_ain_inotify",
        "_ain_watched",
        "logger",
    )

    def __init__(self, name: str | None = None):
        self._aiohttp_apps = defaultdict[_Bind, web.Application](web.Application)
        self._aiohttp_ids = set[_Id]()
        self._ain_inotify: Inotify | None = None
        self._ain_watched = defaultdict[Watch, list[_FileCbInfo]](list)
        self.logger = getLogger(name or "girl")

    def event_web(self, bind: str | PurePath, method: MethodStr, path: str):
        """ """
        if isinstance(bind, str) and ":" in bind:
            host, _, port = bind.partition(":")
            bindd = ("127.0.0.1" if "localhost" == host else host, int(port))
        else:
            bindd = PurePath(StdPath(bind).resolve())

        id = f"{bind} {method} {path}"

        @_reload_guard(id)
        def adder(fn: HttpHandler):
            if id in self._aiohttp_ids:
                raise ValueError("event already observed")

            ret_fn = fn  # HACK: circumvent type narrowing being dum

            if inspect.isasyncgenfunction(fn):

                async def wrapper(req: web.Request):
                    world = self._world(id)
                    gen = fn(world, req)
                    res: web.Response = await anext(gen)
                    # may resume in the background after early response,
                    # the session's world handle is kept live until then
                    t = asyncio.create_task(anext(gen, None))
                    # `fut.result` will re-raise if there was an exception
                    t.add_done_callback(lambda fut: self._close(world) or fut.result())
                    return res

            elif inspect.iscoroutinefunction(fn):

                async def wrapper(req: web.Request):
                    world = self._world(id)
                    try:
                        res: web.Response = await fn(world, req)
                    finally:
                        await self._close(world)
                    return res

            else:
                raise TypeError("handler should be async def with optionally a yield")

            self._aiohttp_apps[bindd].router.add_route(method, path, wrapper)
            self._aiohttp_ids.add(id)
            return ret_fn

        return adder

    def event_file(self, dirname: str | PurePath, fileglob: str):
        """ """
        # need to hackishly elevate to path just to resolve and test is_dir
        dirname = StdPath(dirname).resolve()
        if not dirname.is_dir():
            raise NotADirectoryError(dirname)
        dirname = PurePath(dirname)
        mask = Mask.CREATE | Mask.CLOSE_WRITE | Mask.EXCL_UNLINK | Mask.ONLYDIR

        id = f"{dirname}/{fileglob}"

        @_reload_guard(id)
        def adder(fn: FileHandler):
            if id in {id for l in self._ain_watched.values() for _, id, _ in l}:
                raise ValueError("event already observed")

            if self._ain_inotify is None:
                self._ain_inotify = Inotify()

            search = (watch for watch in self._ain_watched if dirname == watch.path)
            watch = next(search, None) or self._ain_inotify.add_watch(dirname, mask)
            self._ain_watched[watch].append((fileglob, id, fn))
            return fn

        return adder

    def _world(self, id: str):
        return World(id)

    async def _close(self, world: World):
        # HACK: silence private usage in friend class
        await getattr(world, "_close")()

    async def _file_watch_loop(self):
        if self._ain_inotify is None:
            return
        try:
            self.logger.info("file watcher hi")

            async for event in self._ain_inotify:
                if event.watch is None or event.path is None or event.name is None:
                    continue

                search = (
                    (id, fn)
                    for pat, id, fn in self._ain_watched[event.watch]
                    if fnmatch(str(event.name), pat)
                )
                found = next(search, None)
                if not found:
                    continue

                id, fn = found
                world = self._world(id)
                try:
                    await fn(world, Path(event.path))
                except asyncio.CancelledError:
                    raise
                except BaseException:
                    self.logger.error(f"handling event {event!r}", exc_info=True)
                finally:
                    await self._close(world)

        finally:
            # XXX: this a point that makes an app's run non (sequencially at least)
            #      re-entrant, ie you'd have to re-create the app with re-applying the
            #      decorators to be able to run it again; tho it likely doesn't matter
            self._ain_inotify.close()

    async def __call__(self):
        """ """

        async def _serv(bind: _Bind, app: web.Application):
            runn = web.AppRunner(app, handle_signals=True)  # ig so?
            await runn.setup()
            if isinstance(bind, tuple):
                self.logger.info(f"TCP site on {bind}")
                await web.TCPSite(runn, *bind).start()
            else:
                self.logger.info(f"Unix site on {bind}")
                await web.UnixSite(runn, str(bind)).start()
            return runn

        file_watch_task = asyncio.create_task(self._file_watch_loop())
        runners = await asyncio.gather(*(_serv(*p) for p in self._aiohttp_apps.items()))

        self.logger.info("running")
        try:
            while True:
                await asyncio.sleep(3600)
                self.logger.info("alive")
        except KeyboardInterrupt:
            pass
        finally:
            self.logger.info("stopping")
            await asyncio.gather(*(runn.cleanup() for runn in runners))
            file_watch_task.cancel()
            await file_watch_task

    def run(self):
        asyncio.run(self())
