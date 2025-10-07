"""A collection of managment procs."""

import asyncio
import sys
from codeop import compile_command
from collections.abc import Awaitable
from datetime import datetime
from fnmatch import fnmatchcase
from functools import wraps
from logging import getLogger
from pdb import Pdb
from pydoc import Helper
from traceback import format_exception
from typing import Callable
from typing import TypeVar

from ..app import App
from ..world import World

_logger = getLogger(__name__)

_Afn_ = TypeVar("_Afn_", bound=Callable[..., Awaitable[object]])


def _proc(rfn: _Afn_) -> _Afn_:
    @wraps(rfn)
    async def wfn(*a: ..., app: App | None = None, io: Interact | None = None):
        ka = dict[str, object]()
        if "app" in rfn.__annotations__:
            ka["app"] = app
        if "io" in rfn.__annotations__:
            ka["io"] = io
        return await rfn(*a, **ka)

    setattr(wfn, "_is_proc", True)
    r: ... = wfn
    return r


class Interact:
    """ """

    def __init__(
        self,
        abreadline: Callable[[], Awaitable[bytes]],
        abwriteflush: Callable[[bytes], Awaitable[None]] | None,
    ):
        self.abreadline = abreadline
        self.abwriteflush = abwriteflush
        self._buf = bytearray()
        self._loop = asyncio.get_event_loop()

    def sync(self, co: Awaitable[object], /, timeout: float | None = None) -> object:
        return asyncio.run_coroutine_threadsafe(co, self._loop).result(timeout)

    async def aflush(self):
        if self.abwriteflush:
            await self.abwriteflush(bytes(self._buf))
        self._buf.clear()

    def readline(self):
        fut = asyncio.run_coroutine_threadsafe(self.abreadline(), self._loop)
        try:
            return fut.result().decode()
        except ConnectionError as exc:
            raise EOFError from exc

    def writeflush(self, data: str):
        self.write(data)
        self.flush()

    def flush(self):
        fut = asyncio.run_coroutine_threadsafe(self.aflush(), self._loop)
        try:
            fut.result()
        except ConnectionError:
            pass

    def write(self, data: str):
        self._buf.extend(data.encode())


@_proc
async def a(a: str, n: int = 1):
    return "coucou " + a * n


@_proc
async def interact(*, app: App, io: Interact):
    def inner():
        io.write("*interactive*\n")

        help = Helper(input=io, output=io)  # (default help tries to pager)
        locs = globs = dict[str, object](app=app, io=io, help=help)
        while ...:
            try:
                io.writeflush(">>> ")
                src = io.readline()
                try:
                    sym = "eval"
                    co = compile_command(src, symbol=sym)
                except SyntaxError:  # not an expression, maybe statement
                    sym = "exec"
                    co = compile_command(src, symbol=sym)
                if co is None:  # partial source; requires more
                    for l in iter(lambda: io.writeflush("... ") or io.readline(), "\n"):
                        src += l
                    co = compile_command(src, symbol=sym)
            except EOFError:
                return
            except SyntaxError as exc:
                io.writeflush("".join(format_exception(exc)))
                continue

            try:
                assert co
                if (r := eval(co, locs, globs)) is not None:
                    io.writeflush(repr(r) + "\n")
                    locs["_"] = r
            except SystemExit:
                break
            except BaseException as exc:
                io.writeflush("".join(format_exception(exc)))

        io.write(f"now exiting interact...\n")

    await asyncio.to_thread(inner)


@_proc
async def lshandlers(filt: str = "all:*", /, *, app: App):
    """
    cron:*
    file:*
    web:*
    """
    kind, found, pat = filt.partition(":")
    if not found:
        kind, pat = "all", filt
    return sorted(
        id
        for id in {
            *(app.cron.handlers() if kind in {"all", "cron"} else ()),
            *(app.file.handlers() if kind in {"all", "file"} else ()),
            *(app.web.handlers() if kind in {"all", "web"} else ()),
        }
        if fnmatchcase(id, pat)
    )


@_proc
async def lsevents(
    filt: str = "all:*",
    min_ts: float | str | datetime = 0,
    max_ts: float | str | datetime = 10e10,
    any_tag: set[str] | list[str] | None = None,
    /,
    *,
    app: App,
):
    if isinstance(min_ts, str):
        min_ts = datetime.fromisoformat(min_ts)
    if isinstance(min_ts, datetime):
        min_ts = min_ts.timestamp()
    if isinstance(max_ts, str):
        max_ts = datetime.fromisoformat(max_ts)
    if isinstance(max_ts, datetime):
        max_ts = max_ts.timestamp()
    if max_ts <= min_ts:
        raise ValueError(f"broken timestamp range: {max_ts} <= {min_ts}")
    return {
        id: await app.store.listruns(
            id,
            min_ts=min_ts,
            max_ts=max_ts,
            any_tag={t.strip() for t in any_tag or () if t.strip()},
        )
        for id in await lshandlers(filt, app=app)
    }


@_proc
async def lsdata(runid: str, /, *, app: App):
    return await app.store.retrieverun(runid)


class _RawPdb:
    def __init__(self, is_new: bool, io: Interact):
        self.is_new = is_new
        self._io = io
        self._loop = asyncio.get_event_loop()

    def _breakpoint(self, *, header: str | None = None):
        d = Pdb(stdin=self._io, stdout=self._io)
        d.use_rawinput = False
        if header:
            d.message(header)
        """ disabled for now, not sure what i want of it...
        # search for a user-code frame so it's not jarring to debug
        f = sys._getframe()
        while f and str(f.f_globals["__name__"]).startswith("girl."):
            f = f.f_back
        # if we went as far back as to hit the `asyncio.run(innermost)`
        # then it means we didn't even reach into the user function yet
        # (eg. `loading`s to re-assemble the `events.web.Request` object)
        if f and str(f.f_globals["__name__"]).startswith("asyncio."):
            # at minima be outside of the pacifier but xxx don't like it
            f = sys._getframe().f_back.f_back
        '''"""
        f = sys._getframe(2)  # '''
        d.set_trace(f)

    def storing(self, world: "World", key: str, ts: float, data: bytes):
        self._breakpoint(header=f"storing {key} @{ts}")

    def loading(self, world: "World", key: str, ts: float, data: bytes) -> bytes:
        self._breakpoint(header=f"loading {key} @{ts}")
        return data

    def performing(
        self,
        world: "World",
        fn: Callable[..., object],
        *args: ...,
        **kwargs: ...,
    ):
        self._breakpoint(header=f"performing {fn!r}")
        world._pacifier = None
        r = fn(*args, **kwargs)
        world._pacifier = self
        return r


@_proc
async def doevent(
    id: str,
    runid: str | None = None,
    payload: bytes | str | None = None,
    *,
    app: App,
    io: Interact,
):
    if runid is not None and payload is not None:
        raise ValueError("cannot have both 'runid' and 'payload'")
    for ev in (app.cron, app.file, app.web):
        if id in ev.handlers():
            handler = ev.handler(id)
            break
    else:
        raise ValueError(f"event handler for {id!r} not found")

    if runid is None and not isinstance(payload, bytes):
        payload = payload.encode() if payload else b""
    assert payload is None or isinstance(payload, bytes)

    def inner():
        "this gets sent to an isolated thread.."

        async def innermore():
            "..which gets its own loop so it can have its own async stuff"
            async with World(app, id, _RawPdb(runid is None, io), runid=runid) as world:
                await handler.fake(world, payload)

        # the `io: Interact` will still ask for tasks to be ran on the main thread
        # (which is where its connection was created anyways); so when doing eg a
        # `readline`, this_thread's loop will wait on the top-level task and its
        # chain of dependencies which will block on said `readline` which sent a
        # task for the main thread's loop to handle; it also means that pacifier
        # can now be written sync to the condition that it does't send to main loop
        # a task that may itself send something to main loop (..?)
        asyncio.run(innermore())

    await asyncio.to_thread(inner)
