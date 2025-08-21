from copy import deepcopy

from .base import Base
from .base import LoadedRun


class BackendMemory(Base):
    """ """

    def __init__(self):
        self._runs = dict[str, dict[str, LoadedRun]]()

    async def storerun(self, id: str, runid: str, run: LoadedRun):
        self._runs.setdefault(id, {})[runid] = run

        import json

        with open("/tmp/memory.json", "w") as fuck:
            json.dump(self._runs, fuck, indent=3, default=repr)

    async def loadrun(self, id: str, runid: str):
        return deepcopy(self._runs[id][runid])

    async def listruns(self, id: str):
        return [(ts, runid) for runid, (ts, _) in self._runs.get(id, {}).items()]

    async def __aenter__(self):
        pass

    async def __aexit__(self, *_):
        pass
