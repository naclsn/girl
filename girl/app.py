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

    def ready(self, cb: Callable[[], Awaitable[None]]):
        """ """
        self._readies.append(cb)
        return cb

    async def __call__(self):
        """ """
        async with self.store, self.cron, self.file, self.web:
            await asyncio.gather(*(cb() for cb in self._readies))

            _logger.info("Running")
            try:
                h = 0
                while True:
                    await asyncio.sleep(3600)
                    h += 1
                    _logger.info(f"Alive ~{h}h")

            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

            finally:
                _logger.info("Stopping")

    def run(self):
        try:
            asyncio.run(self())
        except KeyboardInterrupt:
            pass
