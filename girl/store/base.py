from abc import ABC
from abc import abstractmethod
from time import time
from types import TracebackType

from ..world import World

LoadedRun = dict[str, list[tuple[float, bytes]]]  # XXX: wth


class Base(ABC):
    """ """

    @abstractmethod
    async def storerun(self, id: str, runid: str, run: LoadedRun):
        """ """

    @abstractmethod
    async def loadrun(self, id: str, runid: str) -> LoadedRun:
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
        assert not world._pacifier
        pair = (world.id, world.runid)
        self._ongoing[pair].setdefault(key, []).append((time(), data))
        world._counter += 1

    def load(self, world: World, key: str) -> bytes:
        """ """
        assert world._pacifier
        pair = (world.id, world.runid)
        res = self._ongoing[pair][key][world._counter]
        world._counter += 1
        return res[1]

    async def beginrun(self, world: World):
        """
        namin is crap; called when a World obj is entered
        - pacifier (replayin) loadall once so load() can be sync
        - no pacifier (real event) not much ig
        """
        pair = (world.id, world.runid)
        if world._pacifier:
            if pair not in self._ongoing:
                run = await self._backend.loadrun(world.id, world.runid)
                self._ongoing.setdefault(pair, run)
        else:
            self._ongoing.setdefault(pair, {})

    async def finishrun(self, world: World):
        """
        namin is crap; called when a World obj is exited
        - pacifier (replayin) drop loaded stuff
        - no pacifier (real event) saveall to backing
        """
        if world._pacifier:
            del self._ongoing[(world.id, world.runid)]
        else:
            run = self._ongoing.pop((world.id, world.runid))
            await self._backend.storerun(world.id, world.runid, run)

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
