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
    """Lightweight dataclass representing meta information on a run."""

    ts: float
    runid: str
    tags: set[str]


@dataclass(frozen=True, slots=True)
class RunInfoFull(RunInfoPartial):
    """Heavyweight dataclass extending :class:`RunInfoPartial`."""

    data: dict[str, tuple[float, bytes]]


class Base(ABC):
    """The trait a class must implement to be eligible as a backend.

    A backend stores data related to a run. The schema is described
    by the :class:`RunInfoFull` class. :attr:`RunInfoPartial.runid`
    is unique by itself; that is even though ``id`` is given when
    storing, it must not be needed for retrieval.

    See the related class :class:`Store`.

    This is described as an abstract base class so as to have proper
    type tagging and for future proofing.

    Backends should be asynchronous and not block the main thread.

    The backend may implement its own in-storage compression;
    also consider using the ``compress`` and ``decompress``
    arguments to :class:`Store`.
    """

    @abstractmethod
    async def storerun(self, id: str, runid: str, run: RunInfoFull):
        """Store the data associated with a run.

        The run does not exists in the store so far (or it is a bug).
        Runs, as stored, are considered immutable. ``runid`` must be
        sufficient to retrieve the full run.

        This methode is expected to actively and asynchronously store
        and flush data to the backend.
        """

    @abstractmethod
    async def loadrun(self, runid: str) -> RunInfoFull:
        """Load the data associated with a run.

        This must return all the data associated with a run, which
        may be a heavy operation.
        """

    @abstractmethod
    async def listruns(
        self,
        id: str,
        *,
        min_ts: float,
        max_ts: float,
        any_tag: set[str],
    ) -> list[RunInfoPartial]:
        """List stored runs with a shallow structures.

        The filtering arguments are always given.
        Runs should be filtered akin to::

            min_ts <= run.ts < max_ts
            and (not any_tag or any_tag & run.tags)

        ``min_ts < max_ts`` is always verified. ``min_ts`` can be 0 and
        ``max_ts`` can go up to 10e10 as meaning "infinity".
        ``any_tag`` may be empty, in which case all runs are selected.
        Values in ``any_tag`` may not have been sanitized.
        """

    @abstractmethod
    async def knowntags(self) -> set[str]:
        """List known tags.

        This is expected to be a rather cheap operation:
        the backend should arrange to cache this set.
        """

    @abstractmethod
    async def status(self) -> str:
        """Free-form status report."""

    @abstractmethod
    async def __aenter__(self):
        """Called to start the backend.

        Any creation of directories, file, table, .. may be performed.
        """

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """Called to stop the backend.

        The backend may first finish ongoing transactions.
        """


class Store:
    """Stores data and information for transiting events.

    The :class:`Store` class shells around a backend. External
    backends can be created by implementing :class:`Base`, shipped:
    - :class:`BackendMemory`
    - :class:`BackendSqlite`

    The ``compress`` and ``decompress`` arguments are used at backend
    boundary. These must be :class:`bytes` to :class:`bytes` and will
    be invoked with the whole chunk to compress/decompress. You most
    certainly want it so that::

        decompress(compress(<bytes>)) = <bytes>

    However you should think about it twice whether compression actually
    brings more than it hinders.
    """

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
        """Internal boundary with the backend."""
        if cf := self.compress:
            for key, (ts, data) in run.data.items():
                run.data[key] = ts, cf(data)
        await self._backend.storerun(id, runid, run)

    async def _loadrun(self, runid: str) -> RunInfoFull:
        """Internal boundary with the backend."""
        run = await self._backend.loadrun(runid)
        if df := self.decompress:
            for key, (ts, data) in run.data.items():
                run.data[key] = ts, df(data)
        return run

    def store(self, world: World, key: str, data: bytes):
        """Store ``data`` under ``key`` for the run.

        Note that ``data`` is not stored directly but buffered until
        the run ends (or raises).

        The state of the world should be that of an actual run
        (not replay or injection).

        This is the public interface, still it is very rarely used
        directly but rather through "proxies" (see :class:`World`).
        """
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
        """Load the data stored under ``key`` for this run.

        Note that all the data for the run are already loaded and
        buffered in the store.

        The state of the world should be that of a fake event
        (replay or injection).

        This is the public interface, still it is very rarely used
        directly but rather through "proxies" (see :class:`World`).
        """
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
        """Add a tag to the run.

        The state of the world should be that of an actual run
        (not replay or injection).

        This is the public interface, still it is very rarely used
        directly but rather through "proxies" (see :meth:`World.tag`).
        """
        assert not world._pacifier or world._pacifier.is_new
        self._ongoing[world.id, world.runid].tags.add(tag)

    async def beginrun(self, world: World):
        """Called when begining a run (entering the world object).

        - has pacifier (fake event): load and cache all related data;
        - no pacifier (real event): not much ig

        This is not meant to be used outside library code.
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
        """Called uppon finishing a run (exiting the world object).

        - has pacifier (fake event): related cache is droped;
        - no pacifier (real event): save the run to backend;

        This is not meant to be used outside library code.
        """
        if world._pacifier and not world._pacifier.is_new:
            _logger.debug(f"finishrun({world!r}): has %s", world._pacifier)
            del self._ongoing[world.id, world.runid]
        else:
            run = self._ongoing.pop((world.id, world.runid))
            total = sum(len(data) for _, data in run.data.values())
            _logger.info(f"flush {world!r} {len(run.data)} items {total} bytes")
            await self._backend.storerun(world.id, world.runid, run)
            await world.app.hook.submit.trigger(world.id, world.runid, run.ts, run.tags)

    async def loadrun(self, runid: str):
        """Public interface to load all the data of a saved run.

        The result is a :class:`RunInfoFull` (contains the ``data``).
        """
        return await self._loadrun(runid)

    async def listruns(
        self,
        id: str,
        *,
        min_ts: float,
        max_ts: float,
        any_tag: set[str],
    ) -> list[RunInfoPartial]:
        """List the saved runs.

        The results are :class:`RunInfoPartial` (contains no ``data``).
        """
        return await self._backend.listruns(
            id,
            min_ts=min_ts,
            max_ts=max_ts,
            any_tag=any_tag,
        )

    async def knowntags(self) -> set[str]:
        """All known tags across all run.

        Store backends are expected to cache this set,
        this operation should be rather cheap.
        """
        return await self._backend.knowntags()

    async def __aenter__(self):
        """Delegate to :meth:`Base.__aenter__`."""
        return await self._backend.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """Delegate to :meth:`Base.__aexit__`."""
        return await self._backend.__aexit__(exc_type, exc_value, traceback)
