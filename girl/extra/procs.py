"""A collection of managment procs."""

import asyncio
from codeop import compile_command
from collections.abc import Awaitable
from fnmatch import fnmatch
from functools import wraps
from logging import getLogger
from traceback import format_exception
from typing import Callable
from typing import TypeVar

from ..app import App

_logger = getLogger(__name__)

_Afn_ = TypeVar("_Afn_", bound=Callable[..., Awaitable[object]])


def _proc(rfn: _Afn_) -> _Afn_:
    @wraps(rfn)
    async def wfn(*a: ..., app: App, io: Interact):
        ka = dict[str, object]()
        if "app" in rfn.__annotations__:
            ka["app"] = app
        if "io" in rfn.__annotations__:
            ka["io"] = io
        return await rfn(*a, **ka)

    setattr(wfn, "_is_proc", True)
    return wfn


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
        asyncio.run_coroutine_threadsafe(self.aflush(), self._loop).result()

    def write(self, data: str):
        self._buf.extend(data.encode())


@_proc
async def a(a: str, n: int = 1):
    return "coucou " + a * n


@_proc
async def interact(*, app: App, io: Interact):
    def inner():
        io.write("*interactive*\n")

        locs = globs = dict[str, object](app=app, io=io)
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
async def lsevents(filt: str = "all:*", /, *, app: App):
    """
    file:*
    web:*
    """
    kind, found, pat = filt.partition(":")
    if not found:
        pat = filt
    return sorted(
        name
        for name in {
            *(app.file.handlers() if kind in {"all", "file"} else ()),
            *(app.web.handlers() if kind in {"all", "web"} else ()),
        }
        if fnmatch(name, pat)
    )
