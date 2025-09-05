import asyncio
from collections.abc import Awaitable
from logging import getLogger
from typing import Callable

from .events import EventsCron
from .events import EventsFile
from .events import EventsWeb
from .store import Store
from .store.base import Base as BackendBase

_logger = getLogger(__name__)


class App:
    """ """

    def __init__(self, store_backend: BackendBase):
        self.store = Store(store_backend)
        self.cron = EventsCron(self)
        self.file = EventsFile(self)
        self.web = EventsWeb(self)
        self._readies = list[Callable[[], Awaitable[None]]]()

    def summary(self) -> str:
        return self.cron.summary() + self.file.summary() + self.web.summary()

    def ready(self, cb: Callable[[], Awaitable[None]]):
        """ """
        self._readies.append(cb)
        return cb

    async def _status(self):
        try:
            with open("/proc/self/status") as st:
                status = dict(l.split(":", 1) for l in st)
        except BaseException as e:
            _logger.warning("cannot read /proc/self/status")
            return

        _logger.info("status:")
        for n in ("VmPeak", "VmSize", "Threads"):
            _logger.info(f"    {n}: {status[n].strip()}")

        backend = self.store._backend
        try:
            _logger.info(f"    {type(backend).__name__}: {await backend.status()}")
        except BaseException as e:
            _logger.warning("cannot get store `backend.status()`")
            return

    async def __call__(self):
        """ """
        async with self.store, self.cron, self.file, self.web:
            await asyncio.gather(*(cb() for cb in self._readies))

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

    def run(self):
        try:
            asyncio.run(self())
        except KeyboardInterrupt:
            pass
