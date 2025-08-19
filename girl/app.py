import asyncio
from logging import getLogger

from .events import EventsCron
from .events import EventsFile
from .events import EventsWeb
from .store import Store

_logger = getLogger(__name__)


class App:
    """ """

    def __init__(self):
        from .store import BackendMemory  # XXX: tmp wip

        self.store = Store(BackendMemory())
        self.cron = EventsCron(self)
        self.file = EventsFile(self)
        self.web = EventsWeb(self)

    async def __call__(self):
        """ """
        async with self.store, self.cron, self.file, self.web:
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
