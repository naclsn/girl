from abc import ABC
from types import TracebackType
from abc import abstractmethod
from ..world import World

_LoadedRun = dict[str, list[bytes]]


class Base(ABC):
    """ """

    @abstractmethod
    async def store(self, id: str, runid: str, key: str, counter: int, data: bytes):
        """ """

    @abstractmethod
    async def loadall(self, id: str, runid: str) -> _LoadedRun:
        """ """

    @abstractmethod
    async def sync(self, id: str, runid: str):
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

    def __init__(self):
        self._backend: Base = ...
        self._ongoing = dict[tuple[str, str], _LoadedRun]()

    async def store(self, world: World, key: str, data: bytes):
        """ """
        await self._backend.store(world.id, world.runid, key, world._counter, data)
        world._counter += 1

    async def load(self, world: World, key: str) -> bytes:
        """ """
        assert world._pacifier
        pair = (world.id, world.runid)
        stuff = self._ongoing.get(pair) or self._ongoing.setdefault(
            pair, await self._backend.loadall(world.id, world.runid)
        )
        res = stuff[key][world._counter]
        world._counter += 1
        return res

    async def flush(self, world: World):
        """
        namin is crap; called when a World obj is closed
        - pacifier (replayin) drop loaded stuff
        - no pacifier (real event) idk but any flushin
        """
        if world._pacifier:
            del self._ongoing[(world.id, world.runid)]
        else:
            await self._backend.sync(world.id, world.runid)

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
