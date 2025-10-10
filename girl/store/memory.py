from copy import deepcopy

from .base import Base
from .base import RunInfoFull
from .base import RunInfoPartial


class BackendMemory(Base):
    """ """

    def __init__(self):
        self._runs = dict[str, dict[str, RunInfoFull]]()
        self._tags = set[str]()

    async def storerun(self, id: str, runid: str, run: RunInfoFull):
        self._runs.setdefault(id, {})[runid] = run
        self._tags.update(run.tags)

    async def loadrun(self, runid: str):
        bag = next(runs for runs in self._runs.values() if runid in runs)
        return deepcopy(bag[runid])

    async def listruns(
        self,
        id: str,
        *,
        min_ts: float,
        max_ts: float,
        any_tag: set[str],
    ):
        return [
            RunInfoPartial(run.ts, runid, run.tags)
            for runid, run in self._runs.get(id, {}).items()
            if min_ts <= run.ts < max_ts and any_tag & run.tags
        ]

    async def knowntags(self):
        return self._tags.copy()

    async def status(self):
        return "(hellow)"

    async def __aenter__(self):
        pass

    async def __aexit__(self, *_):
        pass
