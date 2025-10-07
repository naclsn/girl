import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from logging import getLogger
from typing import Generic
from typing import TypeVarTuple

from .events import EventsCron
from .events import EventsFile
from .events import EventsWeb
from .store import Store
from .store.base import Base as BackendBase

_logger = getLogger(__name__)

_P = TypeVarTuple("_P")


class _Hook(Generic[*_P]):
    def __init__(self, name: str):
        self.name = name
        self._cbs = set[Callable[[*_P], Awaitable[None]]]()

    def __call__(self, cb: Callable[[*_P], Awaitable[None]]):
        self._cbs.add(cb)
        return cb

    def remove(self, cb: Callable[[*_P], Awaitable[None]]):
        self._cbs.remove(cb)

    async def trigger(self, *ar: *_P):
        r = await asyncio.gather(*(it(*ar) for it in self._cbs), return_exceptions=True)
        for err in filter(None, r):
            _logger.error(f"in hook {self.name!r}", exc_info=err)


class _AppHooks:
    def __init__(self):
        self.start = _Hook[()]("start")
        self.submit = _Hook[str, str, float, set[str]]("submit")
        self.stop = _Hook[()]("stop")


class App:
    """ """

    def __init__(self, store_backend: BackendBase):
        self.hook = _AppHooks()
        self.store = Store(store_backend)
        self.cron = EventsCron(self)
        self.file = EventsFile(self)
        self.web = EventsWeb(self)
        self._readies = set[Callable[[], Awaitable[None]]]()

    def summary(self) -> str:
        return self.cron.summary() + self.file.summary() + self.web.summary()

    def ready(self, cb: Callable[[], Awaitable[None]]):
        """ """
        self._readies.add(cb)
        return cb

    async def _status(self):
        try:
            with open("/proc/self/status") as st:
                status = dict(l.split(":", 1) for l in st)
        except BaseException as e:
            _logger.warning("cannot read /proc/self/status", exc_info=e)
            return

        _logger.info("status:")
        for n in ("VmPeak", "VmSize", "Threads"):
            _logger.info(f"    {n}: {status.get(n, '?').strip()}")

        backend = self.store._backend
        try:
            _logger.info(f"    {type(backend).__name__}: {await backend.status()}")
        except BaseException as e:
            _logger.warning("cannot get store `backend.status()`", exc_info=e)
            return

    async def __call__(self):
        """ """
        async with self.store, self.cron, self.file, self.web:
            await asyncio.gather(*(cb() for cb in self._readies))

            await self.hook.start.trigger()
            _logger.info("Running")
            try:
                h = 0
                while ...:
                    await asyncio.sleep(3600)
                    h += 1
                    _logger.info(f"Alive ~{h}h")
                    if 0 == h % 24:
                        await self._status()

            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

            finally:
                _logger.info("Stopping")
                await self.hook.stop.trigger()

    def run(self):
        try:
            asyncio.run(self())
        except KeyboardInterrupt:
            pass
