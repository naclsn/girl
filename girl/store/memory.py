from .base import Base
from collections import defaultdict


class BackendMemory(Base):
    """ """

    def __init__(self):
        self._d: ... = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    async def store(self, id: str, runid: str, key: str, counter: int, data: bytes):
        self._d[id][runid][key].append(data)

    async def loadall(self, id: str, runid: str):
        return self._d[id][runid]

    async def sync(self, id: str, runid: str):
        pass

    async def __aenter__(self):
        pass

    async def __aexit__(self, *_):
        pass
