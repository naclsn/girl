import asyncio
from logging import getLogger

from .events import EventsFile
from .events import EventsWeb

_logger = getLogger(__name__)


class App:
    """ """

    def __init__(self, name: str | None = None):
        self.file = EventsFile()
        self.web = EventsWeb()

    async def __call__(self):
        """ """
        async with self.file, self.web:
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
