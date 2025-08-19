import asyncio
from collections.abc import Awaitable
from datetime import datetime
from datetime import timedelta
from logging import getLogger
from typing import Callable
from typing import Literal
from typing import TypedDict

from .. import app
from ..world import World
from .base import Base
from .base import Handler

CronHandler = Callable[[World], Awaitable[None]]

_logger = getLogger(__name__)

MONTHS = [
    ("january", "jan"),
    ("february", "feb"),
    ("march", "mar"),
    ("april", "apr"),
    ("may", "may"),
    ("june", "jun", "june"),
    ("july", "jul", "july"),
    ("august", "aug"),
    ("september", "sep", "sept"),
    ("october", "oct"),
    ("november", "nov"),
    ("december", "dec"),
]


class OnSpecificDates(TypedDict, total=False):
    year: int
    month: int | str
    day: int
    hour: int
    minute: int
    second: int


class _Schedule:
    __slots__ = ()

    def __init__(self, _):
        pass

    def __str__(self):
        assert not "done"

    def __next__(self) -> datetime:
        assert not "done"


class EventsCron(Base):
    def __init__(self, app: "app.App"):
        self._app = app
        self._handlers = dict[str, Handler[CronHandler]]()

        self._scheds = list[tuple[_Schedule, Handler[CronHandler]]]()

    def event(
        self,
        specific: OnSpecificDates | None = None,
        /,
        *,
        after: datetime | None = None,
        before: datetime | None = None,
        interval: timedelta | None = None,
    ):
        """ """

        if after is not None and before is not None and before <= after:
            raise ValueError(f"'after' must precede 'before': {before!r} <= {after!r}")

        if specific is not None and interval is not None:
            raise ValueError("cannot specify both on specific dates and at an interval")

        if specific is not None and isinstance(smonth := specific.get("month"), str):
            smonth = smonth.strip().lower()
            for month, nam in enumerate(MONTHS):
                if smonth in nam:
                    break
            else:
                raise ValueError(f"invalid month name {smonth!r}")
            specific["month"] = month

        if interval is not None:
            after = after or datetime.now()

        sched = _Schedule(...)

        id = str(sched)

        def adder(fn: CronHandler):
            if id in self._handlers:
                raise ValueError("event already observed")

            handler = Handler(id, fn)
            self._scheds.append((sched, handler))
            self._handlers[id] = handler
            return fn

        return adder

    def handlers(self):
        return set(self._handlers)

    def handler(self, id: str):
        return self._handlers[id]

    async def _task_make(self, id: str, fn: CronHandler):
        async with World(self._app, id, False) as world:
            await fn(world)

    def _task_done(self, task: asyncio.Task[None]):
        self._running.remove(task)
        if task.cancelled():
            return
        if e := task.exception():
            _logger.error("Task %s raised an exception:", task, exc_info=e)

    async def _loop(self):
        self._running = set[asyncio.Task[None]]()

        try:
            while self._scheds:
                upcoming = datetime.max
                handler = None

                for k, (sched, h) in reversed(list(enumerate(self._scheds))):
                    # removes schedules that are definitively done
                    if (dt := next(sched, None)) is None:
                        del self._scheds[k]
                        continue
                    if dt < upcoming:
                        upcoming, handler = dt, h
                if handler is None:
                    continue

                await asyncio.sleep((upcoming - datetime.now()).total_seconds())

                task = asyncio.create_task(self._task_make(handler.id, handler.fn))
                self._running.add(task)
                task.add_done_callback(self._task_done)

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

        finally:
            await asyncio.gather(*(t for t in self._running if t.cancel()))

    async def __aenter__(self):
        self._task = asyncio.create_task(self._loop())

    async def __aexit__(self, *_):
        self._task.cancel()
        await self._task
