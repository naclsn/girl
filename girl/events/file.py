import asyncio
import json
from collections import defaultdict
from collections.abc import Awaitable
from fnmatch import fnmatch
from logging import getLogger
from pathlib import Path as StdPath
from pathlib import PurePath
from typing import Callable
from typing import TypeVar

from asyncinotify import Inotify
from asyncinotify import Mask
from asyncinotify import Watch

from .. import app
from ..world import World
from .base import Base
from .base import Handler

_logger = getLogger(__name__)


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

    __slots__ = ()
    _world: World | None = None

    def read_bytes(self):
        if self._world and self._world._pacifier and not self._world._pacifier.is_new:
            return self._world.app.store.load(self._world, str(self.resolve()))

        data = super().read_bytes()
        if self._world:
            self._world.app.store.store(self._world, str(self.resolve()), data)
        return data

    def write_bytes(self, data: bytes):
        if self._world and self._world._pacifier:
            self._world._pacifier.performing(self._world, Path.write_bytes, self, data)
            return

        super().write_bytes(data)

    def read_text(self):
        return self.read_bytes().decode()

    def write_text(self, data: str):
        self.write_bytes(data.encode())

    def read_json(self):
        return json.loads(self.read_text())

    def write_json(self, data: object):
        self.write_text(json.dumps(data))


# - Having only CREATE can/will trigger too early (not done writing yet).
# - Having only CLOSE_WRITE misses eg fifo/socket (never closed until used).
# - Having CREATE + CLOSE_WRITE creates double-events.
# So we have both but we test for file type; only regular files call handler
# on CLOSE_WRITE, other (in fifo/socket/symlink/dir/dev..) on CREATE.
_MASK = Mask.CREATE | Mask.CLOSE_WRITE | Mask.EXCL_UNLINK | Mask.ONLYDIR
_PatAndId = tuple[str, str]

FileHandler = Callable[[World, Path], Awaitable[None]]
_FileHandler_ = TypeVar("_FileHandler_", bound=FileHandler)


class EventsFile(Base):
    def __init__(self, app: "app.App"):
        self._app = app
        self._handlers = dict[str, Handler[FileHandler]]()

        self._inotify: Inotify | None = None
        self._watched = defaultdict[Watch, list[_PatAndId]](list)

    def summary(self):
        txt = ""
        watch = list = None
        for watch, list in self._watched.items():
            txt += f"Watching {watch.path}:\n"
            for pat, id in list:
                txt += f"    {pat} {self._handlers[id].fn}\n"
        return txt

    def event(self, dirname: str | PurePath, fileglob: str):
        """ """
        # need to hackishly elevate to path just to resolve and test is_dir
        dirname = StdPath(dirname).resolve()
        if not dirname.is_dir():
            raise NotADirectoryError(dirname)
        dirname = PurePath(dirname)

        id = f"{dirname}/{fileglob}"

        def adder(fn: _FileHandler_):
            if id in self._handlers:
                raise ValueError("event already observed")

            if self._inotify is None:
                self._inotify = Inotify()

            search = (watch for watch in self._watched if dirname == watch.path)
            watch = next(search, None) or self._inotify.add_watch(dirname, _MASK)
            self._watched[watch].append((fileglob, id))
            self._handlers[id] = Handler(id, fn, EventsFile._fake)
            return fn

        return adder

    def handlers(self):
        return set(self._handlers)

    def handler(self, id: str):
        return self._handlers[id]

    @staticmethod
    async def _fake(world: World, payload: bytes | None, fn: FileHandler):
        if payload is None:
            payload = world.app.store.load(world, "*path*")
        path = Path(payload.decode())
        path._world = world
        await fn(world, path)

    async def _task_make(self, id: str, fn: FileHandler, path: str):
        async with World(self._app, id, None) as world:
            _logger.debug(f"File event with {world!r}")
            pathh = world.file(path).resolve()
            world.app.store.store(world, "*path*", bytes(pathh))
            await fn(world, pathh)

    def _task_done(self, task: asyncio.Task[None]):
        self._running.remove(task)
        if task.cancelled():
            return
        if e := task.exception():
            _logger.error("Task %s raised an exception:", task, exc_info=e)

    async def _loop(self):
        if self._inotify is None:
            return

        self._running = set[asyncio.Task[None]]()

        try:
            watch = list = None
            for watch, list in self._watched.items():
                _logger.info(f"Watching {watch.path}:")
                for pat, id in list:
                    _logger.info(f"    {pat} {self._handlers[id].fn}")
            del watch, list

            async for event in self._inotify:
                if event.watch is None or event.path is None or event.name is None:
                    continue
                # see comment above `_MASK` as to why these checks
                reg = event.path.is_file() and not event.path.is_symlink()
                if event.mask & Mask.CREATE if reg else event.mask & Mask.CLOSE_WRITE:
                    _logger.debug(f"Skipping {event.path} because {repr(event.mask)}")
                    continue

                search = (
                    (id, self._handlers[id].fn)
                    for pat, id in self._watched[event.watch]
                    if fnmatch(str(event.name), pat)
                )
                found = next(search, None)
                if not found:
                    continue

                task = asyncio.create_task(self._task_make(*found, str(event.path)))
                self._running.add(task)
                task.add_done_callback(self._task_done)

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

        finally:
            await asyncio.gather(*(t for t in self._running if t.cancel()))
            self._inotify.close()

    async def __aenter__(self):
        self._task = asyncio.create_task(self._loop())

    async def __aexit__(self, *_):
        self._task.cancel()
        await self._task
