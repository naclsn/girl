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
            _logger.info("running")
            try:
                while True:
                    await asyncio.sleep(3600)
                    _logger.info("alive")
            except KeyboardInterrupt:
                pass
            finally:
                _logger.info("stopping")

    def run(self):
        asyncio.run(self())
