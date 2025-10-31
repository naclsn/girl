import asyncio
from collections.abc import Awaitable
from collections.abc import Iterable
from datetime import datetime
from logging import getLogger
from typing import Callable
from typing import TypeVar

from .. import app
from ..world import World
from .base import Base
from .base import Handler

CronHandler = Callable[[World], Awaitable[None]]
_CronHandler_ = TypeVar("_CronHandler_", bound=CronHandler)

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
DAYS = [
    ("sunday", "sun"),
    ("monday", "mon"),
    ("tuesday", "tue", "tues"),
    ("wednesday", "wed"),
    ("thursday", "thu", "thur", "thurs"),
    ("friday", "fri"),
    ("saturday", "sat"),
]


class _Schedule:
    __slots__ = ("_minutes", "_hours", "_days", "_months", "_after", "_before")

    @staticmethod
    def _valid(it: int | Iterable[int] | None, r: range, unit: str):
        ls = [it] if isinstance(it, int) else sorted(set(it)) if it else []
        if not ls:
            return ls
        if ls[0] not in r:
            raise ValueError(f"invalid {unit}: {ls[0]} not in {r}")
        if ls[-1] not in r:
            raise ValueError(f"invalid {unit}: {ls[-1]} not in {r}")
        return ls

    def __init__(
        self,
        minutes: int | Iterable[int],
        hours: int | Iterable[int],
        days: int | Iterable[int],  # weekdays: str | Iterable[str]
        months: int | str | Iterable[int | str],
        after: datetime | None = None,
        before: datetime | None = None,
    ):
        months = iter((months,) if isinstance(months, (int, str)) else months)
        self._minutes = self._valid(minutes, range(0, 60), "minutes")
        self._hours = self._valid(hours, range(0, 24), "hours")
        self._days = self._valid(days, range(1, 32), "days")
        self._months = list[int]()
        for m in months:
            if isinstance(m, str):
                m = m.strip().lower()
                for month, nam in enumerate(MONTHS):
                    if m in nam:
                        break
                else:
                    raise ValueError(f"invalid month name {m!r}")
                m = month
            self._months.append(m)
        self._months = self._valid(self._months, range(1, 13), "months")
        self._after = after
        self._before = before

    @staticmethod
    def _present(ls: list[int]):
        if not ls:
            return "*"
        s = ""
        k = 0
        while k < len(ls):
            s += f",{ls[k]}"
            k += 1
            if k < len(ls) and ls[k] - 1 == ls[k - 1]:
                while k < len(ls) and ls[k] - 1 == ls[k - 1]:
                    k += 1
                s += f"-{ls[k - 1]}"
        return s[1:]

    def __str__(self):
        minutes = self._present(self._minutes)
        hours = self._present(self._hours)
        days = self._present(self._days)
        months = self._present(self._months)
        r = f"{minutes} {hours} {days} {months}"
        if self._after:
            r = f"{self._after!r} <= {r}"
        if self._before:
            r = f"{r} <= {self._before!r}"
        return r

    def __next__(self) -> datetime:
        now = datetime.now()
        if self._after and now < self._after:
            return self._after
        if self._before and self._before < now:
            raise StopIteration
        for year in range(now.year, now.year + 2):
            for month in self._months or range(1, 13):
                for day in self._days or range(1, 32):
                    try:
                        datetime(year, month, day)
                    except ValueError:
                        break  # invalid day for month (eg 31)
                    for hour in self._hours or range(0, 24):
                        for minute in self._minutes or range(0, 60):
                            candidate = datetime(year, month, day, hour, minute)
                            if candidate <= now:
                                continue
                            return candidate
        raise StopIteration


class EventsCron(Base):
    def __init__(self, app: "app.App"):
        self._app = app
        self._handlers = dict[str, Handler[CronHandler]]()

        self._scheds = list[tuple[_Schedule, Handler[CronHandler]]]()

    def summary(self):
        txt = "Cron tab:\n"
        for sched, handler in self._scheds:
            txt += f"    {sched} {handler.fn}\n"
        return txt

    def event(
        self,
        minutes: int | Iterable[int],
        hours: int | Iterable[int],
        days: int | Iterable[int],  # weekdays: str | Iterable[str]
        months: int | str | Iterable[int | str],
        *,
        after: datetime | None = None,
        before: datetime | None = None,
    ):
        """ """

        if after is not None and before is not None and before <= after:
            raise ValueError(f"'after' must precede 'before': {before!r} <= {after!r}")
        sched = _Schedule(minutes, hours, days, months, after, before)

        id = str(sched)

        def adder(fn: _CronHandler_):
            if id in self._handlers:
                raise ValueError("event already observed")

            self._handlers[id] = Handler(id, fn, EventsCron._fake)
            self._scheds.append((sched, self._handlers[id]))
            return fn

        return adder

    def handlers(self):
        return set(self._handlers)

    def handler(self, id: str):
        return self._handlers[id]

    @staticmethod
    async def _fake(world: World, payload: bytes | None, fn: CronHandler):
        _ = payload
        await fn(world)

    async def _task_make(self, id: str, fn: CronHandler):
        async with World(self._app, id, None) as world:
            _logger.debug(f"Cron event with {world!r}")
            await fn(world)

    def _task_done(self, task: asyncio.Task[None]):
        self._running.remove(task)
        if task.cancelled():
            return
        if e := task.exception():
            _logger.error("Task %s raised an exception:", task, exc_info=e)

    async def _loop(self):
        if not self._scheds:
            return
        self._running = set[asyncio.Task[None]]()

        try:
            _logger.info("Cron tab:")
            for sched, handler in self._scheds:
                _logger.info(f"    {sched} {handler.fn}")

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
