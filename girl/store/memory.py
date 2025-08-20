from collections import defaultdict

from .base import Base
from .base import LoadedRun


class BackendMemory(Base):
    """ """

    def __init__(self):
        self._d: ... = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    async def storerun(self, id: str, runid: str, run: LoadedRun):
        self._d[id][runid] = run

        import json

        with open("/tmp/memory.json", "w") as fuck:
            json.dump(self._d, fuck, indent=3, default=repr)

    async def loadrun(self, id: str, runid: str):
        return self._d[id][runid]

    async def __aenter__(self):
        pass

    async def __aexit__(self, *_):
        pass
