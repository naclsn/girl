from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from logging import getLogger
from time import time
from types import TracebackType

from ..world import World

_logger = getLogger(__name__)

_CompressFunc = Callable[[bytes], bytes]
_DecompressFunc = Callable[[bytes], bytes]


@dataclass(frozen=True, slots=True)
class RunInfoPartial:
    ts: float
    runid: str
    tags: set[str]


@dataclass(frozen=True, slots=True)
class RunInfoFull(RunInfoPartial):
    data: dict[str, tuple[float, bytes]]


class Base(ABC):
    """ """

    @abstractmethod
    async def storerun(self, id: str, runid: str, run: RunInfoFull):
        """ """

    @abstractmethod
    async def loadrun(self, runid: str) -> RunInfoFull:
        """ """

    @abstractmethod
    async def listruns(
        self,
        id: str,
        *,
        min_ts: float,
        max_ts: float,
        any_tag: set[str],
    ) -> list[RunInfoPartial]:
        """ """

    @abstractmethod
    async def status(self) -> str:
        """ """

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

    def __init__(
        self,
        backend: Base,
        /,
        *,
        compress: _CompressFunc | None = None,
        decompress: _DecompressFunc | None = None,
    ):
        self._backend = backend
        self._ongoing = dict[tuple[str, str], RunInfoFull]()
        self.compress = compress
        self.decompress = decompress

    async def _storerun(self, id: str, runid: str, run: RunInfoFull):
        if cf := self.compress:
            for key, (ts, data) in run.data.items():
                run.data[key] = ts, cf(data)
        await self._backend.storerun(id, runid, run)

    async def _loadrun(self, runid: str) -> RunInfoFull:
        run = await self._backend.loadrun(runid)
        if df := self.decompress:
            for key, (ts, data) in run.data.items():
                run.data[key] = ts, df(data)
        return run

    def store(self, world: World, key: str, data: bytes):
        """ """
        # pacifier and context are responsible for asserting that
        # the run (runid) *does not* exists
        assert not world._pacifier or world._pacifier.is_new
        ts = time()

        entries = self._ongoing[world.id, world.runid].data
        if key in entries:
            search_free = (f"{key} ({n})" for n in range(99))
            key = next(nkey for nkey in search_free if nkey not in entries)
        entries[key] = ts, data

        if world._pacifier:
            _logger.debug(f"store({world!r}, {key!r}): has %s", world._pacifier)
            world._pacifier.storing(world, key, ts, data)

    def load(self, world: World, key: str) -> bytes:
        """ """
        # pacifier and context are responsible for asserting that
        # the run (runid) *actually* exists
        assert world._pacifier and not world._pacifier.is_new

        entries = self._ongoing[world.id, world.runid].data
        if key not in entries:
            search_present = (f"{key} ({n})" for n in range(99))
            key = next(nkey for nkey in search_present if nkey in entries)
        ts, data = entries[key]

        _logger.debug(f"load({world!r}, {key!r}): has %s", world._pacifier)
        data = world._pacifier.loading(world, key, ts, data)
        return data

    def tagrun(self, world: World, tag: str):
        assert not world._pacifier or world._pacifier.is_new
        self._ongoing[world.id, world.runid].tags.add(tag)

    async def beginrun(self, world: World):
        """
        namin is crap; called when a World obj is __aenter__
        - pacifier (replayin) loadall once so load() can be sync
        - no pacifier (real event) not much ig
        """
        pair = world.id, world.runid
        if world._pacifier and not world._pacifier.is_new:
            _logger.debug(f"beginrun({world!r}): has %s", world._pacifier)
            if pair not in self._ongoing:
                run = await self._loadrun(world.runid)
                self._ongoing.setdefault(pair, run)
        else:
            self._ongoing.setdefault(pair, RunInfoFull(time(), world.runid, set(), {}))

    async def finishrun(self, world: World):
        """
        namin is crap; called when a World obj is __aexit__
        - pacifier (replayin) drop loaded stuff
        - no pacifier (real event) saveall to backing
        """
        if world._pacifier and not world._pacifier.is_new:
            _logger.debug(f"finishrun({world!r}): has %s", world._pacifier)
            del self._ongoing[(world.id, world.runid)]
        else:
            run = self._ongoing.pop((world.id, world.runid))
            total = sum(len(data) for _, data in run.data.values())
            _logger.info(f"flush {world!r} {len(run.data)} items {total} bytes")
            await self._backend.storerun(world.id, world.runid, run)
            await world.app.hook.submit.trigger(world.id, world.runid, run.ts, run.tags)

    async def loadrun(self, runid: str):
        """ """
        return await self._loadrun(runid)

    async def listruns(
        self,
        id: str,
        *,
        min_ts: float,
        max_ts: float,
        any_tag: set[str],
    ) -> list[RunInfoPartial]:
        """ """
        return await self._backend.listruns(
            id,
            min_ts=min_ts,
            max_ts=max_ts,
            any_tag=any_tag,
        )

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
