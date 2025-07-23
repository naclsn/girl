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


class EventsFile(Base):
    def __init__(self):
        self.__inotify: Inotify | None = None
        self.__watched = defaultdict[Watch, list[_FileCbInfo]](list)

    def event(self, dirname: str | PurePath, fileglob: str):
        """ """
        # need to hackishly elevate to path just to resolve and test is_dir
        dirname = StdPath(dirname).resolve()
        if not dirname.is_dir():
            raise NotADirectoryError(dirname)
        dirname = PurePath(dirname)
        mask = Mask.CREATE | Mask.CLOSE_WRITE | Mask.EXCL_UNLINK | Mask.ONLYDIR

        id = f"{dirname}/{fileglob}"

        def adder(fn: FileHandler):
            if id in {id for l in self.__watched.values() for _, id, _ in l}:
                raise ValueError("event already observed")

            if self.__inotify is None:
                self.__inotify = Inotify()

            search = (watch for watch in self.__watched if dirname == watch.path)
            watch = next(search, None) or self.__inotify.add_watch(dirname, mask)
            self.__watched[watch].append((fileglob, id, fn))
            return fn

        return adder

    @staticmethod
    async def _task(id: str, fn: FileHandler, path: Path):
        async with World(id) as world:
            await fn(world, path)

    async def _loop(self):
        if self.__inotify is None:
            return

        try:
            _logger.info("file watcher hi")

            async for event in self.__inotify:
                if event.watch is None or event.path is None or event.name is None:
                    continue

                search = (
                    (id, fn)
                    for pat, id, fn in self.__watched[event.watch]
                    if fnmatch(str(event.name), pat)
                )
                found = next(search, None)
                if not found:
                    continue

                t = asyncio.create_task(EventsFile._task(*found, Path(event.path)))
                # TODO: something of t

        finally:
            self.__inotify.close()

    async def __aenter__(self):
        self.__task = asyncio.create_task(self._loop())

    async def __aexit__(self, *_):
        self.__task.cancel()
        await self.__task
