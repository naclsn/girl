import asyncio
from collections import defaultdict
from collections.abc import Awaitable
from fnmatch import fnmatch
from logging import getLogger
from pathlib import Path as StdPath
from pathlib import PurePath
from typing import Callable

from asyncinotify import Inotify
from asyncinotify import Mask
from asyncinotify import Watch

from .base import Base
from ..world import Path
from ..world import World

FileHandler = Callable[[World, Path], Awaitable[None]]

_FileCbInfo = tuple[str, str, FileHandler]

_logger = getLogger(__name__)

# - Having only CREATE can/will trigger too early (not done writing yet).
# - Having only CLOSE_WRITE misses eg fifo/socket (never closed until used).
# - Having CREATE + CLOSE_WRITE creates double-events.
# So we have both but we test for file type; only regular files call handler
# on CLOSE_WRITE, other (in fifo/socket/symlink/dir/dev..) on CREATE.
_MASK = Mask.CREATE | Mask.CLOSE_WRITE | Mask.EXCL_UNLINK | Mask.ONLYDIR


class EventsFile(Base):
    def __init__(self):
        self._inotify: Inotify | None = None
        self._watched = defaultdict[Watch, list[_FileCbInfo]](list)

    def event(self, dirname: str | PurePath, fileglob: str):
        """ """
        # need to hackishly elevate to path just to resolve and test is_dir
        dirname = StdPath(dirname).resolve()
        if not dirname.is_dir():
            raise NotADirectoryError(dirname)
        dirname = PurePath(dirname)

        id = f"{dirname}/{fileglob}"

        def adder(fn: FileHandler):
            if id in {id for l in self._watched.values() for _, id, _ in l}:
                raise ValueError("event already observed")

            if self._inotify is None:
                self._inotify = Inotify()

            search = (watch for watch in self._watched if dirname == watch.path)
            watch = next(search, None) or self._inotify.add_watch(dirname, _MASK)
            self._watched[watch].append((fileglob, id, fn))
            return fn

        return adder

    async def _take_make(self, id: str, fn: FileHandler, path: Path):
        async with World(id) as world:
            await fn(world, path)

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
                for pat, _, _ in list:
                    _logger.info(f"    {pat}")
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
                    (id, fn)
                    for pat, id, fn in self._watched[event.watch]
                    if fnmatch(str(event.name), pat)
                )
                found = next(search, None)
                if not found:
                    continue

                task = asyncio.create_task(self._take_make(*found, Path(event.path)))
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
