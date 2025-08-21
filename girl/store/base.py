from abc import ABC
from abc import abstractmethod
from time import time
from types import TracebackType

from ..world import World

LoadedRun = tuple[float, dict[str, tuple[float, bytes]]]  # XXX: wth


class Base(ABC):
    """ """

    @abstractmethod
    async def storerun(self, id: str, runid: str, run: LoadedRun):
        """ """

    @abstractmethod
    async def loadrun(self, id: str, runid: str) -> LoadedRun:
        """ """

    @abstractmethod
    async def listruns(self, id: str) -> list[tuple[float, str]]:
        """ """

    # @abstractmethod
    # async def search(self) -> ...:
    #     """ """

    @abstractmethod
    async def __aenter__(self):
        """ """

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """ """


class Store:
    """ """

    def __init__(self, backend: Base):
        self._backend = backend
        self._ongoing = dict[tuple[str, str], LoadedRun]()

    def store(self, world: World, key: str, data: bytes):
        """ """
        # pacifier and context are responsible for asserting that
        # the run (runid) *does not* exists
        assert not world._pacifier or world._pacifier.is_new
        pair = world.id, world.runid
        ts = time()

        entries = self._ongoing[pair][1]
        if key in entries:
            search_free = (f"{key} ({n})" for n in range(99))
            key = next(nkey for nkey in search_free if nkey not in entries)
        entries[key] = ts, data

        if world._pacifier:
            world._pacifier.storing(world, key, ts, data)

    def load(self, world: World, key: str) -> bytes:
        """ """
        # pacifier and context are responsible for asserting that
        # the run (runid) *actually* exists
        assert world._pacifier and not world._pacifier.is_new
        pair = world.id, world.runid

        entries = self._ongoing[pair][1]
        if key not in entries:
            search_present = (f"{key} ({n})" for n in range(99))
            key = next(nkey for nkey in search_present if nkey in entries)
        ts, data = entries[key]

        data = world._pacifier.loading(world, key, ts, data)
        return data

    async def beginrun(self, world: World):
        """
        namin is crap; called when a World obj is entered
        - pacifier (replayin) loadall once so load() can be sync
        - no pacifier (real event) not much ig
        """
        pair = world.id, world.runid
        if world._pacifier and not world._pacifier.is_new:
            if pair not in self._ongoing:
                run = await self._backend.loadrun(world.id, world.runid)
                self._ongoing.setdefault(pair, run)
        else:
            self._ongoing.setdefault(pair, (time(), {}))

    async def finishrun(self, world: World):
        """
        namin is crap; called when a World obj is exited
        - pacifier (replayin) drop loaded stuff
        - no pacifier (real event) saveall to backing
        """
        if world._pacifier and not world._pacifier.is_new:
            del self._ongoing[(world.id, world.runid)]
        else:
            run = self._ongoing.pop((world.id, world.runid))
            await self._backend.storerun(world.id, world.runid, run)

    async def listruns(self, id: str) -> list[tuple[float, str]]:
        """ """
        return await self._backend.listruns(id)

    async def __aenter__(self):
        """ """
        return await self._backend.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """ """
        return await self._backend.__aexit__(exc_type, exc_value, traceback)
