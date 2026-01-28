import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from logging import getLogger
from typing import Generic
from typing import TypedDict
from typing import TypeVarTuple

import aiohttp
import aiohttp.abc
import aiohttp.helpers
import aiohttp.typedefs

from .events import EventsCron
from .events import EventsFile
from .events import EventsWeb
from .store import Store

_logger = getLogger(__name__)

_P = TypeVarTuple("_P")


class _Hook(Generic[*_P]):
    """Dead simple hook system for a set of even on :class:`App`,
    see :class:`_AppHooks`.
    """

    def __init__(self, name: str):
        self.name = name
        self._cbs = set[Callable[[*_P], Awaitable[None]]]()

    def __call__(self, cb: Callable[[*_P], Awaitable[None]]):
        """Register a callback for this hook.

        If using a custom class with ``__call__`` op, the class
        must also be hashable.
        """
        self._cbs.add(cb)
        return cb

    def remove(self, cb: Callable[[*_P], Awaitable[None]]):
        """Remove a callback.

        This works by python object identity (ie it must be
        the same object that was given to :meth:`__call__`).
        A :class:`KeyError` is raised otherwise.
        """
        self._cbs.remove(cb)

    async def trigger(self, *ar: *_P):
        """Trigger the hook. Every registered callback are invoked.

        This should not be done manually outside library code.
        """
        r = await asyncio.gather(*(it(*ar) for it in self._cbs), return_exceptions=True)
        for err in filter(None, r):
            _logger.error(f"in hook {self.name!r}", exc_info=err)


class _AppHooks:
    """The set of hook :class:`App` invokes.

    These names are meant to be used as decorator to callback functions:

    - @ :attr:`start`
    - @ :attr:`submit`
    - @ :attr:`stop`
    """

    def __init__(self):
        self.start = _Hook[*()]("start")
        """Triggered when the app starts, after @ :meth:`App.ready`;
        contrary to @ :meth:`App.ready` exceptions are ignored.
        """
        self.submit = _Hook[str, str, float, set[str]]("submit")
        """Triggered when finishing a "real event" run, after storage.
        The arguments are the id, runid, timestamp and set of tags.
        """
        self.stop = _Hook[*()]("stop")
        """Triggered when the app stops, before stopping events."""


class _AppSettings_WorldWeb(TypedDict, total=False):
    """See :class:`aiohttp.ClientSession`."""
    cookies: aiohttp.typedefs.LooseCookies
    headers: aiohttp.typedefs.LooseHeaders
    proxy: aiohttp.typedefs.StrOrURL
    proxy_auth: aiohttp.BasicAuth
    skip_auto_headers: Iterable[str]
    auth: aiohttp.BasicAuth
    json_serialize: aiohttp.typedefs.JSONEncoder
    cookie_jar: aiohttp.abc.AbstractCookieJar
    raise_for_status: bool | Callable[[aiohttp.ClientResponse], Awaitable[None]]
    read_timeout: float
    conn_timeout: float
    ssl_shutdown_timeout: float
    auto_decompress: bool
    trust_env: bool
    requote_redirect_url: bool
    trace_configs: list[aiohttp.TraceConfig]
    read_bufsize: int
    max_line_size: int
    max_field_size: int
    middlewares: Sequence[aiohttp.ClientMiddlewareType]


class _AppSettings(TypedDict, total=False):
    """Settings for various parts of an :class:`App`."""

    world_web: _AppSettings_WorldWeb
    """This is passed to :class:`aiohttp.ClientSession`."""
    slug_pattern: str | int
    """This is passed to :func:`coolname.generate_slug`."""
    tag_max_len: int
    """Max acceptable length for tags, defaults to 40."""
    status_report_hours: int
    """Print a free-form status report every so many (default 24) hours."""


class App:
    """The central orchestration class.

    This class centralizes the settings, data store and event engines.
    Event handlers are to be registered through one of these:

    - :attr:`cron` (:class:`EventsCron`)
    - :attr:`file` (:class:`EventsFile`)
    - :attr:`web` (:class:`EventsWeb`)

    The life-cycle of an app is implemented by :meth:`__call__` as follow:

    1. the store is started;
    2. the various event engines are started;
    3. @ :meth:`ready` handlers are ran;
    4. runtime (events are served to handlers and run data stored);
    5. on interruption/termination, all stops in reverse order.

    (Hooks have been omitted.)
    """

    def __init__(self, store: Store, app_settings: _AppSettings | None = None):
        self.hook = _AppHooks()
        self.store = store
        """Backing store for past runs' data."""
        self.cron = EventsCron(self)
        """The :class:`EventsCron` event engine."""
        self.file = EventsFile(self)
        """The :class:`EventsFile` event engine."""
        self.web = EventsWeb(self)
        """The :class:`EventsWeb` event engine."""
        self._readies = set[Callable[[], Awaitable[None]]]()
        self.settings = app_settings or {}

    def summary(self) -> str:
        """Free-form summary of events with registered handlers."""
        return self.cron.summary() + self.file.summary() + self.web.summary()

    def ready(self, cb: Callable[[], Awaitable[None]]):
        """Special event (decorator) for when the app is getting ready.

        These are invoked right after starting the event engines,
        before processing anything else. In particular, an exception
        at this point aborts everything.
        """
        self._readies.add(cb)
        return cb

    async def _status(self):
        """Free-form summary of the runtime.

        This is of course not sufficient for monitoring."""
        try:
            with open("/proc/self/status") as st:
                status = dict(l.split(":", 1) for l in st)
        except BaseException as e:
            _logger.warning("cannot read /proc/self/status", exc_info=e)
            return

        _logger.info("status:")
        for n in "VmPeak", "VmSize", "Threads":
            _logger.info(f"    {n}: {status.get(n, '?').strip()}")

        backend = self.store._backend
        try:
            _logger.info(f"    {type(backend).__name__}: {await backend.status()}")
        except BaseException as e:
            _logger.warning("cannot get store `backend.status()`", exc_info=e)
            return

    async def __call__(self):
        """Contextualized async main loop. See :meth:`run`.

        This manages the top-level life cycle. See :class:`App`.
        """
        async with self.store, self.cron, self.file, self.web:
            await asyncio.gather(*(cb() for cb in self._readies))

            await self.hook.start.trigger()
            _logger.info("Running")
            try:
                h = 0
                while ...:
                    await asyncio.sleep(3600)
                    h += 1
                    _logger.info(f"Alive ~{h}h")
                    if 0 == h % self.settings.get("status_report_hours", 24):
                        await self._status()

            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

            finally:
                _logger.info("Stopping")
                await self.hook.stop.trigger()

    def run(self, *, debug: bool | None = None):
        """Sync wrapper to :meth:`__call__`."""
        try:
            asyncio.run(self(), debug=debug)
        except KeyboardInterrupt:
            pass
